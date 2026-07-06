import logging
import os
import re
import anthropic
import json
from google import genai
from google.adk.agents.llm_agent import Agent
from google.adk.runners import InMemoryRunner
from google.genai import types
from app.tools import ReceiptOutput, ComplianceOutput, convert_currency
from app.mcp_server import PolicyEngine
from app.config import settings

# Setup logging
logger = logging.getLogger("ComplianceEnforcer")

# Configure model name
MODEL_NAME = "gemini-2.5-flash"

# Instantiate policy engine to search local policy markdown files
policy_engine = PolicyEngine(data_dir="data")

# Define tools to be registered with the agent
def lookup_policy_tool(country_name: str) -> dict:
    """
    Looks up the compliance rules for a specific country from regional policy documents.
    Returns:
        dict: Policy parameters containing country, currency, vat_rate, dinner_limit, and lodging_limit.
    """
    logger.info(f"Tool execution: lookup_policy_tool for country '{country_name}'")
    policy = policy_engine.lookup_policy(country_name)
    if policy:
        return policy
    return {
        "country": country_name,
        "currency": "USD",
        "vat_rate": 0.0,
        "dinner_limit": 100.0,  # conservative global fallback limits
        "lodging_limit": 200.0,
        "region": "GLOBAL"
    }

def convert_currency_tool(amount: float, from_currency: str, to_currency: str = "USD") -> float:
    """
    Converts amount from a source currency to a target currency (defaults to USD).
    """
    logger.info(f"Tool execution: convert_currency_tool {amount} {from_currency} -> {to_currency}")
    return convert_currency(amount, from_currency, to_currency)


# Define Agent 2: Compliance Enforcer
compliance_agent = Agent(
    name="compliance_enforcer",
    model=MODEL_NAME,
    instruction=(
        "You are an expert corporate compliance auditing agent. Your task is to ingest receipt information "
        "and enforce regional spending policies.\n\n"
        "Please follow these instructions precisely:\n"
        "1. Ingest the ReceiptOutput data: amount, currency, country, has_pii.\n"
        "2. Call `lookup_policy_tool` for the receipt's country to get the local rules.\n"
        "3. Convert the receipt amount to USD using `convert_currency_tool` (this is `amount_usd`).\n"
        "4. Determine the policy limit: Unless the context explicitly mentions lodging, default to using the dinner_limit from the policy. "
        "   Convert this policy limit from the local currency (specified in the policy) to USD using `convert_currency_tool` (this is `policy_limit_usd`).\n"
        "5. Perform compliance validation: compare the amount in USD (`amount_usd`) against the limit in USD (`policy_limit_usd`).\n"
        "   - If `amount_usd` <= `policy_limit_usd`, set is_compliant to True, and excess to 0.0.\n"
        "   - If `amount_usd` > `policy_limit_usd`, set is_compliant to False, and excess to amount_usd - policy_limit_usd.\n"
        "6. Calculate `vat_reclaim` in local currency: multiply the receipt amount by the vat_rate from the policy.\n"
        "7. Call the `set_model_response` tool with the calculated fields to return a valid ComplianceOutput structure."
    ),
    tools=[lookup_policy_tool, convert_currency_tool],
    input_schema=ReceiptOutput,
    output_schema=ComplianceOutput
)

def enforce_compliance(receipt: ReceiptOutput) -> ComplianceOutput | None:
    """
    Validates a structured receipt against company policies using the compliance agent.
    
    Args:
        receipt (ReceiptOutput): The structured output from Agent 1.
        
    Returns:
        ComplianceOutput: Structured compliance results, or None if execution fails.
    """
    logger.info(f"Checking compliance for receipt: {receipt}")
    
    # We use InMemoryRunner to execute the agentic workflow
    runner = InMemoryRunner(agent=compliance_agent)
    runner.auto_create_session = True
    
    try:
        # Pass structured input fields as prompt content
        prompt_text = (
            f"Please check compliance for this receipt:\n"
            f"- Amount: {receipt.amount}\n"
            f"- Currency: {receipt.currency}\n"
            f"- Country: {receipt.country}\n"
            f"- PII Flagged: {receipt.has_pii}"
        )
        
        user_message = types.Content(
            role="user",
            parts=[types.Part(text=prompt_text)]
        )
        
        # Execute agent
        events = runner.run(
            user_id="user_compliance",
            session_id="session_compliance",
            new_message=user_message
        )
        
        final_output = None
        text_output = ""
        for event in events:
            if event.output:
                final_output = event.output
            if hasattr(event, 'content') and event.content:
                try:
                    for part in event.content.parts:
                        if part.text:
                            text_output += part.text
                except Exception:
                    pass
            elif hasattr(event, 'text') and event.text:
                text_output += event.text

        if final_output:
            if isinstance(final_output, ComplianceOutput):
                return final_output
            elif isinstance(final_output, dict):
                return ComplianceOutput(**final_output)
            else:
                logger.error(f"Unexpected compliance enforcer output type: {type(final_output)}")

        if text_output:
            cleaned_text = text_output.replace("```json", "").replace("```", "").strip()
            try:
                compliance_data = json.loads(cleaned_text)
                if isinstance(compliance_data, dict):
                    return ComplianceOutput(**compliance_data)
            except json.JSONDecodeError:
                logger.warning("Failed to decode cleaned JSON from Gemini text output.\nCleaned text:\n%s", cleaned_text)
            except Exception as parse_exc:
                logger.warning("Unexpected error when parsing cleaned Gemini output: %s", parse_exc)

        raise ValueError("No structured output returned from Agent 2 (Compliance Enforcer).")
        
    except Exception as e:
        logger.warning(f"⚠️ Gemini primary path hit an error or 503 overload: {e}")
        logger.info("Bypassing Anthropic fallback and generating local deterministic compliance report...")

        # Retrieve fallback policy values for the receipt country
        policy = lookup_policy_tool(receipt.country)
        dinner_limit = policy.get("dinner_limit", 20000.0)
        policy_currency = policy.get("currency", receipt.currency)
        vat_rate = policy.get("vat_rate", 0.0)

        # Perform deterministic compliance comparison against the dinner limit
        is_compliant_flag = receipt.amount <= dinner_limit
        audit_status = "COMPLIANT" if is_compliant_flag else "NON_COMPLIANT"
        final_status = "AUTO_APPROVED" if is_compliant_flag else "FLAGGED_FOR_REVIEW"

        # Convert amounts to USD with a local fallback rate if needed
        try:
            amount_usd = round(convert_currency(receipt.amount, receipt.currency, "USD"), 2)
        except Exception:
            amount_usd = round(receipt.amount / 156.0, 2) if receipt.currency.upper() == "JPY" else round(receipt.amount, 2)

        try:
            policy_limit_usd = round(convert_currency(dinner_limit, policy_currency, "USD"), 2)
        except Exception:
            policy_limit_usd = round(dinner_limit / 156.0, 2) if policy_currency.upper() == "JPY" else round(dinner_limit, 2)

        excess = round(max(0.0, amount_usd - policy_limit_usd), 2)
        vat_reclaim = round(receipt.amount * vat_rate, 2)

        fallback_report = f"""
        # Global Compliance Audit Report (Local Backup Mode)

        ## Receipt Overview
        - **Country:** {receipt.country}
        - **Submitted Amount:** {receipt.amount:.2f} {receipt.currency}
        - **Converted USD Amount:** ~${amount_usd:.2f} USD

        ## Corporate Policy Verification
        - **Policy Regional Limit:** {dinner_limit:.2f} {policy_currency} (Dinner Limit)
        - **Audit Status:** {audit_status}
        - **Final Status:** {final_status}
        - **PII Guardrail Check:** {'PASSED' if not receipt.has_pii else 'REQUIRES REVIEW'}

        ## Auditor Summary
        The expense was evaluated using a local deterministic fallback path. "{final_status}" was selected based on policy rule comparison.
        """

        logger.info(f"Generated deterministic compliance fallback report:\n{fallback_report.strip()}")

        return ComplianceOutput(
            is_compliant=is_compliant_flag,
            amount_usd=amount_usd,
            policy_limit=policy_limit_usd,
            excess=excess,
            vat_reclaim=vat_reclaim
        )
