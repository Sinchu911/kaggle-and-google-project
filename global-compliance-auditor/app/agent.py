import logging
from app.agent1_parser import parse_receipt
from app.agent2_compliance import enforce_compliance
from app.agent3_verification import verify_transaction
from app.agent4_guardrail import generate_compliance_report

# Setup logging
logger = logging.getLogger("PipelineOrchestrator")

class Orchestrator:
    """
    The master Orchestrator for the Global Compliance Auditor system.
    Sequentially chains all 4 specialized agents into a unified pipeline.
    """
    def __init__(self):
        logger.info("Initializing Global Compliance Auditor pipeline orchestrator.")

    def audit_expense(self, raw_receipt_text: str) -> dict | None:
        """
        Processes a raw unstructured receipt text through the multi-agent pipeline:
        1. Parse receipt text to extract structured amounts and flags (Agent 1).
        2. Validate receipt fields against regional policies and convert currencies (Agent 2).
        3. Decide if the transaction needs manager review or auto-approval (Agent 3).
        4. Apply safety checks and generate a comprehensive audit report (Agent 4).
        
        Args:
            raw_receipt_text (str): The raw text submitted by the employee.
            
        Returns:
            dict: A consolidated dictionary containing outputs from all agents:
                {
                    "receipt": ReceiptOutput,
                    "compliance": ComplianceOutput,
                    "verification": VerificationOutput,
                    "report": str  # Markdown compliance report summary
                }
                Or None if processing fails completely at the parser stage.
        """
        logger.info("Starting end-to-end audit pipeline...")
        
        # Step 1: Run Agent 1 (Receipt Parser)
        receipt = parse_receipt(raw_receipt_text)
        if not receipt:
            logger.error("Pipeline failed: Step 1 (Receipt Parser) returned None.")
            return None
        logger.info(f"Step 1 Complete. Parsed Receipt: {receipt}")

        # Step 2: Run Agent 2 (Compliance Enforcer)
        compliance = enforce_compliance(receipt)
        if not compliance:
            logger.error("Pipeline failed: Step 2 (Compliance Enforcer) returned None.")
            return None
        logger.info(f"Step 2 Complete. Compliance Results: {compliance}")

        # Step 3: Run Agent 3 (Human Verification Router)
        verification = verify_transaction(receipt, compliance)
        if not verification:
            logger.error("Pipeline failed: Step 3 (Human Verification Router) returned None.")
            return None
        logger.info(f"Step 3 Complete. Verification Route: {verification}")

        # Step 4: Run Agent 4 (Final Compliance Guardrail)
        report = generate_compliance_report(receipt, compliance, verification)
        logger.info("Step 4 Complete. Final Compliance Report Generated.")
        
        return {
            "receipt": receipt,
            "compliance": compliance,
            "verification": verification,
            "report": report
        }
