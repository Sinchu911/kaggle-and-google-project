import pytest
from unittest.mock import patch, MagicMock
from app.tools import ReceiptOutput, ComplianceOutput
from app.agent3_verification import VerificationOutput, verify_transaction
from app.agent4_guardrail import generate_compliance_report

# ==========================================
# Agent 3: Human Verification Router Tests
# ==========================================

def test_verify_transaction_deterministic_auto_approved():
    """Test deterministic auto-approval logic when no PII is found and no excess is present."""
    receipt = ReceiptOutput(amount=85.50, currency="EUR", country="Italy", has_pii=False)
    compliance = ComplianceOutput(
        is_compliant=True,
        amount_usd=94.00,
        policy_limit=110.00,
        excess=0.0,
        vat_reclaim=18.81
    )
    # Trigger with settings or patch to force fallback path or mock runner
    with patch('app.agent3_verification.InMemoryRunner') as mock_runner_class:
        mock_event = MagicMock()
        mock_event.output = VerificationOutput(status="AUTO_APPROVED", reason="Clean and compliant")
        mock_runner_instance = MagicMock()
        mock_runner_instance.run.return_value = [mock_event]
        mock_runner_class.return_value = mock_runner_instance
        
        result = verify_transaction(receipt, compliance)
        
        assert result is not None
        assert result.status == "AUTO_APPROVED"
        assert "Clean" in result.reason
        mock_runner_class.assert_called_once()


def test_verify_transaction_pii_triggers_human_review():
    """Test routing to PENDING_HUMAN_REVIEW when PII is detected."""
    receipt = ReceiptOutput(amount=85.50, currency="EUR", country="Italy", has_pii=True)
    compliance = ComplianceOutput(
        is_compliant=True,
        amount_usd=94.00,
        policy_limit=110.00,
        excess=0.0,
        vat_reclaim=18.81
    )
    with patch('app.agent3_verification.InMemoryRunner') as mock_runner_class:
        mock_event = MagicMock()
        mock_event.output = VerificationOutput(status="PENDING_HUMAN_REVIEW", reason="PII detected")
        mock_runner_instance = MagicMock()
        mock_runner_instance.run.return_value = [mock_event]
        mock_runner_class.return_value = mock_runner_instance
        
        result = verify_transaction(receipt, compliance)
        
        assert result is not None
        assert result.status == "PENDING_HUMAN_REVIEW"
        assert "PII" in result.reason


def test_verify_transaction_excess_triggers_human_review():
    """Test routing to PENDING_HUMAN_REVIEW when the compliance limit is exceeded (excess > 0)."""
    receipt = ReceiptOutput(amount=150.00, currency="USD", country="United States", has_pii=False)
    compliance = ComplianceOutput(
        is_compliant=False,
        amount_usd=150.00,
        policy_limit=100.00,
        excess=50.00,
        vat_reclaim=0.0
    )
    with patch('app.agent3_verification.InMemoryRunner') as mock_runner_class:
        mock_event = MagicMock()
        mock_event.output = VerificationOutput(status="PENDING_HUMAN_REVIEW", reason="Limit exceeded")
        mock_runner_instance = MagicMock()
        mock_runner_instance.run.return_value = [mock_event]
        mock_runner_class.return_value = mock_runner_instance
        
        result = verify_transaction(receipt, compliance)
        
        assert result is not None
        assert result.status == "PENDING_HUMAN_REVIEW"
        assert "exceeded" in result.reason.lower() or "limit" in result.reason.lower()


def test_verify_transaction_fallback_on_exception():
    """Verify that verify_transaction falls back gracefully to deterministic logic if ADK fails."""
    receipt = ReceiptOutput(amount=85.50, currency="EUR", country="Italy", has_pii=True)
    compliance = ComplianceOutput(
        is_compliant=True,
        amount_usd=94.00,
        policy_limit=110.00,
        excess=0.0,
        vat_reclaim=18.81
    )
    with patch('app.agent3_verification.InMemoryRunner', side_effect=RuntimeError("ADK crashed")), \
         patch('os.getenv', return_value=None):
        result = verify_transaction(receipt, compliance)
        assert result is not None
        assert result.status == "PENDING_HUMAN_REVIEW"
        assert "PII" in result.reason


@patch('app.agent3_verification.InMemoryRunner')
@patch('app.agent3_verification.anthropic.Anthropic')
def test_verify_transaction_fallback_to_claude(mock_anthropic_class, mock_runner_class):
    # Make Gemini runner fail
    mock_runner_instance = MagicMock()
    mock_runner_instance.run.side_effect = Exception("Gemini API Error")
    mock_runner_class.return_value = mock_runner_instance
    
    # Mock Anthropic Client and response
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_tool_use = MagicMock()
    mock_tool_use.type = "tool_use"
    mock_tool_use.name = "verify_transaction"
    mock_tool_use.input = {
        "status": "AUTO_APPROVED",
        "reason": "Claude says it is clean and compliant"
    }
    mock_response.content = [mock_tool_use]
    mock_client.messages.create.return_value = mock_response
    mock_anthropic_class.return_value = mock_client
    
    receipt = ReceiptOutput(amount=85.50, currency="EUR", country="Italy", has_pii=False)
    compliance = ComplianceOutput(
        is_compliant=True,
        amount_usd=94.00,
        policy_limit=110.00,
        excess=0.0,
        vat_reclaim=18.81
    )
    
    # Patch environmental API key to be present so it doesn't return deterministic early
    with patch('os.getenv', return_value="dummy_anthropic_key"):
        result = verify_transaction(receipt, compliance)
        
        assert result is not None
        assert result.status == "AUTO_APPROVED"
        assert "Claude" in result.reason
        
        # Verify Anthropic client was created and called with the correct model and prompt
        mock_anthropic_class.assert_called_once_with(api_key="dummy_anthropic_key")
        mock_client.messages.create.assert_called_once()
        call_kwargs = mock_client.messages.create.call_args[1]
        assert call_kwargs["model"] == "claude-3-5-sonnet-20241022"


# ==========================================
# Agent 4: Final Compliance Guardrail Tests
# ==========================================

def test_generate_compliance_report_fallback():
    """Verify that a high-fidelity Markdown report is generated when API key is missing."""
    receipt = ReceiptOutput(amount=85.50, currency="EUR", country="Italy", has_pii=False)
    compliance = ComplianceOutput(
        is_compliant=True,
        amount_usd=94.00,
        policy_limit=110.00,
        excess=0.0,
        vat_reclaim=18.81
    )
    verification = VerificationOutput(status="AUTO_APPROVED", reason="Transaction is clean and compliant.")
    
    with patch('app.agent4_guardrail.settings') as mock_settings:
        mock_settings.GOOGLE_API_KEY = "MISSING"
        report = generate_compliance_report(receipt, compliance, verification)
        
        assert report is not None
        assert "# Expense Compliance Audit Report" in report
        assert "AUTO_APPROVED" in report
        assert "94.00" in report
        assert "18.81" in report


@patch('app.agent4_guardrail.genai.Client')
def test_generate_compliance_report_api_success(mock_client_class):
    """Verify report generation with mocked Gemini API client."""
    receipt = ReceiptOutput(amount=85.50, currency="EUR", country="Italy", has_pii=False)
    compliance = ComplianceOutput(
        is_compliant=True,
        amount_usd=94.00,
        policy_limit=110.00,
        excess=0.0,
        vat_reclaim=18.81
    )
    verification = VerificationOutput(status="AUTO_APPROVED", reason="Transaction is clean and compliant.")
    
    # Configure mock responses
    mock_response = MagicMock()
    mock_response.text = "# Custom Gemini Markdown Compliance Report\nDecision: AUTO_APPROVED"
    mock_client_instance = MagicMock()
    mock_client_instance.models.generate_content.return_value = mock_response
    mock_client_class.return_value = mock_client_instance
    
    with patch('app.agent4_guardrail.settings') as mock_settings:
        mock_settings.GOOGLE_API_KEY = "dummy_valid_api_key"
        report = generate_compliance_report(receipt, compliance, verification)
        
        assert report is not None
        assert "Custom Gemini Markdown Compliance Report" in report
        assert "Decision: AUTO_APPROVED" in report
        
        mock_client_class.assert_called_once_with(api_key="dummy_valid_api_key")
        mock_client_instance.models.generate_content.assert_called_once()


@patch('app.agent4_guardrail.genai.Client')
@patch('app.agent4_guardrail.anthropic.Anthropic')
def test_generate_compliance_report_fallback_to_claude(mock_anthropic_class, mock_client_class):
    receipt = ReceiptOutput(amount=85.50, currency="EUR", country="Italy", has_pii=False)
    compliance = ComplianceOutput(
        is_compliant=True,
        amount_usd=94.00,
        policy_limit=110.00,
        excess=0.0,
        vat_reclaim=18.81
    )
    verification = VerificationOutput(status="AUTO_APPROVED", reason="Transaction is clean and compliant.")
    
    # Make Gemini Client fail
    mock_client_class.side_effect = Exception("Gemini initialization failed")
    
    # Mock Anthropic response
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_content_block = MagicMock()
    mock_content_block.text = "# Custom Claude Markdown Compliance Report\nDecision: AUTO_APPROVED"
    mock_response.content = [mock_content_block]
    mock_client.messages.create.return_value = mock_response
    mock_anthropic_class.return_value = mock_client
    
    with patch('app.agent4_guardrail.settings') as mock_settings, \
         patch('os.getenv', return_value="dummy_anthropic_key"):
        mock_settings.GOOGLE_API_KEY = "dummy_valid_api_key"
        report = generate_compliance_report(receipt, compliance, verification)
        
        assert report is not None
        assert "Custom Claude Markdown Compliance Report" in report
        assert "Decision: AUTO_APPROVED" in report
        
        mock_anthropic_class.assert_called_once_with(api_key="dummy_anthropic_key")
        mock_client.messages.create.assert_called_once()
        call_kwargs = mock_client.messages.create.call_args[1]
        assert call_kwargs["model"] == "claude-3-5-sonnet-20241022"
