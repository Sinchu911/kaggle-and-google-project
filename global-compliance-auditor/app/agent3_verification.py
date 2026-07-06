import logging
import os
import re
import json
import anthropic
from google.adk.agents.llm_agent import Agent
from google.adk.runners import InMemoryRunner
from google.genai import types
from pydantic import BaseModel, Field
from app.tools import ReceiptOutput, ComplianceOutput

# Setup logging
logger = logging.getLogger("HumanVerificationRouter")

# Model configuration
MODEL_NAME = "gemini-2.5-flash"

class VerificationOutput(BaseModel):
    status: str = Field(
        ...,
        description="The verification status: 'PENDING_HUMAN_REVIEW' or 'AUTO_APPROVED'"
    )
    reason: str = Field(
        ...,
        description="A clear reason string explaining why the status was decided"
    )

# Define Agent 3: Human Verification Router
verification_agent = Agent(
    name="human_verification_router",
    model=MODEL_NAME,
    instruction=(
        "You are a routing agent that evaluates receipt parsing and compliance check results.\n"
        "Your task is to route the transaction for human review or auto-approval.\n\n"
        "Evaluation rules:\n"
        "1. Check the has_pii flag. If has_pii is True, status MUST be 'PENDING_HUMAN_REVIEW' "
        "and reason must explain that PII was detected.\n"
        "2. Check the compliance excess. If excess is greater than 0, status MUST be 'PENDING_HUMAN_REVIEW' "
        "and reason must explain that the limit was exceeded.\n"
        "3. If has_pii is False and excess is 0, status MUST be 'AUTO_APPROVED' with a reason indicating "
        "the expense is clean and compliant.\n\n"
        "You MUST invoke the `set_model_response` tool with the VerificationOutput data."
        "Do not return any explanatory text, markdown fences, or extra content."
        "Return only raw structured JSON/text matching the VerificationOutput schema, with keys 'status' and 'reason'."
    ),
    output_schema=VerificationOutput
)

def verify_transaction(receipt: ReceiptOutput, compliance: ComplianceOutput) -> VerificationOutput | None:
    """
    Evaluates ReceiptOutput and ComplianceOutput to route the transaction for human review or auto-approval.
    """
    logger.info(f"Routing transaction: receipt={receipt}, compliance={compliance}")
    
    # We include a robust deterministic fallback to guarantee compliance safety
    # regardless of API availability or LLM response variations.
    fallback_status = "AUTO_APPROVED"
    fallback_reason = "Transaction is clean and compliant."
    
    if receipt.has_pii:
        fallback_status = "PENDING_HUMAN_REVIEW"
        fallback_reason = "Transaction contains sensitive PII that requires human redaction."
    elif compliance.excess > 0:
        fallback_status = "PENDING_HUMAN_REVIEW"
        fallback_reason = f"Transaction exceeds policy limit by ${compliance.excess:.2f} USD."
        
    def deterministic_fallback() -> VerificationOutput:
        return VerificationOutput(status=fallback_status, reason=fallback_reason)

    def clean_possible_json(text: str) -> str:
        cleaned = re.sub(r"```(?:json)?", "", text, flags=re.IGNORECASE)
        cleaned = re.sub(r"```", "", cleaned)
        return cleaned.strip()

    def normalize_verification_dict(data: dict) -> dict:
        normalized = {}
        for key, value in data.items():
            lower_key = key.strip().lower()
            if lower_key in {"status", "verification_status", "result"}:
                normalized["status"] = str(value).strip().upper()
            elif lower_key in {"reason", "explanation", "details", "message"}:
                normalized["reason"] = str(value).strip()
        return normalized

    def parse_verification_output(payload) -> VerificationOutput | None:
        if isinstance(payload, VerificationOutput):
            return payload
        if isinstance(payload, dict):
            normalized = normalize_verification_dict(payload)
            if normalized.get("status") and normalized.get("reason"):
                return VerificationOutput(**normalized)
            return None
        if isinstance(payload, str):
            cleaned = clean_possible_json(payload)
            try:
                parsed = json.loads(cleaned)
                if isinstance(parsed, dict):
                    normalized = normalize_verification_dict(parsed)
                    if normalized.get("status") and normalized.get("reason"):
                        return VerificationOutput(**normalized)
            except json.JSONDecodeError:
                pass

            status_match = re.search(r"\b(PENDING_HUMAN_REVIEW|AUTO_APPROVED)\b", cleaned, flags=re.IGNORECASE)
            if status_match:
                status_value = status_match.group(1).upper()
                reason = cleaned
                return VerificationOutput(status=status_value, reason=reason)
        return None

    try:
        runner = InMemoryRunner(agent=verification_agent)
        runner.auto_create_session = True
        prompt_text = (
            f"Please evaluate these inputs and return only a JSON object with 'status' and 'reason'.\n"
            f"- Receipt has PII: {receipt.has_pii}\n"
            f"- Compliance excess amount: {compliance.excess}\n"
            f"- Compliance is_compliant status: {compliance.is_compliant}\n"
            f"Do not include any explanation, markdown, or extra text."
        )
        
        user_message = types.Content(
            role="user",
            parts=[types.Part(text=prompt_text)]
        )
        
        events = runner.run(
            user_id="user_verification",
            session_id="session_verification",
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
            parsed_output = parse_verification_output(final_output)
            if parsed_output:
                return parsed_output
            logger.warning("Parsed final_output was not valid; falling back to text parsing.")
        
        if text_output:
            cleaned_text = text_output.replace("```json", "").replace("```", "").strip()
            parsed_output = parse_verification_output(cleaned_text)
            if parsed_output:
                return parsed_output
            logger.warning("Failed to parse raw verifier text output. Cleaned text: %s", cleaned_text)
        
        raise ValueError("No structured output returned from Agent 3 (Verification Router).")

    except Exception as e:
        logger.warning("⚠️ Gemini primary path failed for Agent 3 Verification; attempting Anthropic fallback.")
        try:
            api_key = os.getenv("ANTHROPIC_API_KEY")
            if not api_key:
                logger.warning("ANTHROPIC_API_KEY is not set. Using deterministic fallback.")
                return deterministic_fallback()
            
            client = anthropic.Anthropic(api_key=api_key)
            prompt_text = (
                f"Please evaluate these inputs and verify transaction compliance integrity:\n"
                f"- Receipt has PII: {receipt.has_pii}\n"
                f"- Compliance excess amount: {compliance.excess}\n"
                f"- Compliance is_compliant status: {compliance.is_compliant}\n"
                f"- Receipt Amount: {receipt.amount} {receipt.currency}\n"
                f"- Converted Amount (USD): {compliance.amount_usd}\n"
                f"- Policy Limit (USD): {compliance.policy_limit}\n\n"
                f"Rules:\n"
                f"1. Check if PII is present. If has_pii is True, status MUST be 'PENDING_HUMAN_REVIEW' with a reason indicating PII detection.\n"
                f"2. Check the compliance excess. If excess is greater than 0, status MUST be 'PENDING_HUMAN_REVIEW' with a reason indicating limit exceeded.\n"
                f"3. Otherwise, status MUST be 'AUTO_APPROVED' with a reason indicating clean compliance.\n"
            )
            
            response = client.messages.create(
                model="claude-3-5-sonnet-20241022",
                max_tokens=1000,
                tools=[
                    {
                        "name": "verify_transaction",
                        "description": "Submit structured transaction verification output.",
                        "input_schema": {
                            "type": "object",
                            "properties": {
                                "status": {
                                    "type": "string",
                                    "description": "The verification status: 'PENDING_HUMAN_REVIEW' or 'AUTO_APPROVED'"
                                },
                                "reason": {
                                    "type": "string",
                                    "description": "A clear reason string explaining why the status was decided"
                                }
                            },
                            "required": ["status", "reason"]
                        }
                    }
                ],
                tool_choice={"type": "tool", "name": "verify_transaction"},
                messages=[
                    {"role": "user", "content": prompt_text}
                ]
            )
            
            tool_use = None
            for block in response.content:
                if block.type == "tool_use" and block.name == "verify_transaction":
                    tool_use = block
                    break
            
            if tool_use:
                return VerificationOutput(**tool_use.input)
            
            logger.warning("Anthropic Claude returned no tool call. Using deterministic fallback.")
            return deterministic_fallback()
        except Exception as claude_err:
            logger.warning(
                "⚠️ Anthropic fallback also failed for Agent 3 Verification. Returning deterministic fallback response.",
                exc_info=True
            )
            return deterministic_fallback()
