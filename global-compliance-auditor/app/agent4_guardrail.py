import logging
import os
import anthropic
from google import genai
from app.tools import ReceiptOutput, ComplianceOutput
from app.agent3_verification import VerificationOutput
from app.config import settings

# Setup logging
logger = logging.getLogger("FinalComplianceGuardrail")

# Model configuration
MODEL_NAME = "gemini-2.5-flash"

def generate_compliance_report(
    receipt: ReceiptOutput,
    compliance: ComplianceOutput,
    verification: VerificationOutput
) -> str:
    """
    Performs a final structural safety check on audit results and utilizes
    Gemini 3.5 Flash to format a structured Markdown compliance report summary.
    """
    logger.info("Running Agent 4: Final Compliance Guardrail and Report Generation")
    
    # 1. Structural safety check
    safety_warnings = []
    if compliance.excess < 0:
        safety_warnings.append("WARNING: Compliance excess amount cannot be negative.")
    if verification.status == "AUTO_APPROVED" and compliance.excess > 0:
        safety_warnings.append("WARNING: Transaction has excess spending but was marked as AUTO_APPROVED.")
    if verification.status == "AUTO_APPROVED" and receipt.has_pii:
        safety_warnings.append("WARNING: Transaction contains PII but was marked as AUTO_APPROVED.")
        
    if safety_warnings:
        for warning in safety_warnings:
            logger.warning(warning)
            
    # Formulate the deterministic fallback Markdown report
    fallback_report = f"""# Expense Compliance Audit Report

## Audit Summary
- **Final Decision Status**: {verification.status}
- **Compliance Status**: {"COMPLIANT" if compliance.is_compliant else "NON-COMPLIANT"}
- **Audit Reason**: {verification.reason}

## Financial Details
- **Receipt Amount**: {receipt.amount:.2f} {receipt.currency}
- **Amount (USD Equivalent)**: ${compliance.amount_usd:.2f} USD
- **Policy Limit (USD)**: ${compliance.policy_limit:.2f} USD
- **Excess Amount (USD)**: ${compliance.excess:.2f} USD
- **VAT Reclaim (Local Currency)**: {compliance.vat_reclaim:.2f} {receipt.currency}

## Policy & Safety Diagnostics
- **Country of Origin**: {receipt.country}
- **PII Detected**: {"YES" if receipt.has_pii else "NO"}
"""
    if safety_warnings:
        fallback_report += "\n## Safety Warnings & Violations\n"
        for warning in safety_warnings:
            fallback_report += f"- {warning}\n"

    # If the Google API key is missing or a placeholder, return the fallback report directly
    if not settings or not settings.GOOGLE_API_KEY or settings.GOOGLE_API_KEY == "MISSING":
        logger.info("Google API key is not configured. Returning local high-fidelity compliance report.")
        return fallback_report.strip()

    try:
        # Initialize Google GenAI client
        client = genai.Client(api_key=settings.GOOGLE_API_KEY)
        
        prompt = (
            f"You are the Final Compliance Guardrail agent.\n"
            f"Please perform a final structural safety check and generate a formatted corporate Markdown compliance report summary based on these audit results:\n\n"
            f"Receipt Info:\n"
            f"- Amount: {receipt.amount} {receipt.currency}\n"
            f"- Country: {receipt.country}\n"
            f"- Has PII: {receipt.has_pii}\n\n"
            f"Compliance Info:\n"
            f"- Is Compliant: {compliance.is_compliant}\n"
            f"- Amount in USD: ${compliance.amount_usd:.2f}\n"
            f"- Policy Limit in USD: ${compliance.policy_limit:.2f}\n"
            f"- Excess Amount in USD: ${compliance.excess:.2f}\n"
            f"- VAT Reclaim: {compliance.vat_reclaim} {receipt.currency}\n\n"
            f"Verification Route Decision:\n"
            f"- Status: {verification.status}\n"
            f"- Reason: {verification.reason}\n\n"
            f"Safety Diagnostics / Warnings:\n"
            f"{chr(10).join(safety_warnings) if safety_warnings else 'None'}\n\n"
            f"Please output a professional, structured Markdown report. Ensure it includes:\n"
            f"1. **Summary Table / Block**: final decision status, total amount, converted amount (USD), and compliance status.\n"
            f"2. **Policy Details**: the rules applied (e.g. limit applied, country), excess spending, and calculated VAT reclaim.\n"
            f"3. **Verification & Audit Notes**: reasons for approval or flagging for human review, and any warnings.\n"
            f"Write ONLY the Markdown content. Do not include extra conversational text outside of the Markdown."
        )
        
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=prompt
        )
        
        if response and response.text:
            return response.text.strip()
        
        raise ValueError("Gemini API returned empty text.")
        
    except Exception as e:
        logger.warning("⚠️ Gemini primary path failed for Agent 4 Guardrail! Falling back to Anthropic Claude...")
        try:
            api_key = os.getenv("ANTHROPIC_API_KEY")
            if not api_key:
                logger.error("ANTHROPIC_API_KEY is not set. Falling back to local compliance report.")
                return fallback_report.strip()
            
            client = anthropic.Anthropic(api_key=api_key)
            prompt = (
                f"You are the Final Compliance Guardrail agent.\n"
                f"Please perform a final structural safety check and generate a formatted corporate Markdown compliance report summary based on these audit results:\n\n"
                f"Receipt Info:\n"
                f"- Amount: {receipt.amount} {receipt.currency}\n"
                f"- Country: {receipt.country}\n"
                f"- Has PII: {receipt.has_pii}\n\n"
                f"Compliance Info:\n"
                f"- Is Compliant: {compliance.is_compliant}\n"
                f"- Amount in USD: ${compliance.amount_usd:.2f}\n"
                f"- Policy Limit in USD: ${compliance.policy_limit:.2f}\n"
                f"- Excess Amount in USD: ${compliance.excess:.2f}\n"
                f"- VAT Reclaim: {compliance.vat_reclaim} {receipt.currency}\n\n"
                f"Verification Route Decision:\n"
                f"- Status: {verification.status}\n"
                f"- Reason: {verification.reason}\n\n"
                f"Safety Diagnostics / Warnings:\n"
                f"{chr(10).join(safety_warnings) if safety_warnings else 'None'}\n\n"
                f"Please output a professional, structured Markdown report. Ensure it includes:\n"
                f"1. **Summary Table / Block**: final decision status, total amount, converted amount (USD), and compliance status.\n"
                f"2. **Policy Details**: the rules applied (e.g. limit applied, country), excess spending, and calculated VAT reclaim.\n"
                f"3. **Verification & Audit Notes**: reasons for approval or flagging for human review, and any warnings.\n"
                f"Write ONLY the Markdown content. Do not include extra conversational text outside of the Markdown."
            )
            
            response = client.messages.create(
                model="claude-3-5-sonnet-20241022",
                max_tokens=1500,
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )
            
            if response.content and len(response.content) > 0 and response.content[0].text:
                return response.content[0].text.strip()
            
            logger.warning("Claude API returned empty text. Falling back to local compliance report.")
            return fallback_report.strip()
        except Exception as claude_err:
            logger.error(f"Fallback to Anthropic Claude failed for Agent 4: {claude_err}. Returning fallback report.", exc_info=True)
            return fallback_report.strip()
