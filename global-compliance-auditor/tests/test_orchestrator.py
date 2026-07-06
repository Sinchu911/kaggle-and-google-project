import pytest
from unittest.mock import patch, MagicMock
from app.tools import ReceiptOutput, ComplianceOutput
from app.agent3_verification import VerificationOutput
from app.agent import Orchestrator

@patch('app.agent1_parser.InMemoryRunner')
@patch('app.agent2_compliance.InMemoryRunner')
@patch('app.agent3_verification.InMemoryRunner')
@patch('app.agent4_guardrail.genai.Client')
def test_orchestrator_end_to_end_success(
    mock_client_class_4,
    mock_runner_class_3,
    mock_runner_class_2,
    mock_runner_class_1
):
    """
    Verifies that the Orchestrator executes all 4 agents sequentially
    and returns a consolidated dictionary including the final Markdown report.
    """
    # 1. Setup mock responses for all agents
    
    # Agent 1 mock output
    mock_event_1 = MagicMock()
    mock_event_1.output = ReceiptOutput(amount=85.50, currency="EUR", country="Italy", has_pii=False)
    mock_runner_instance_1 = MagicMock()
    mock_runner_instance_1.run.return_value = [mock_event_1]
    mock_runner_class_1.return_value = mock_runner_instance_1

    # Agent 2 mock output
    mock_event_2 = MagicMock()
    mock_event_2.output = ComplianceOutput(
        is_compliant=True,
        amount_usd=94.00,
        policy_limit=110.00,
        excess=0.0,
        vat_reclaim=18.81
    )
    mock_runner_instance_2 = MagicMock()
    mock_runner_instance_2.run.return_value = [mock_event_2]
    mock_runner_class_2.return_value = mock_runner_instance_2

    # Agent 3 mock output
    mock_event_3 = MagicMock()
    mock_event_3.output = VerificationOutput(
        status="AUTO_APPROVED",
        reason="Transaction is clean and compliant."
    )
    mock_runner_instance_3 = MagicMock()
    mock_runner_instance_3.run.return_value = [mock_event_3]
    mock_runner_class_3.return_value = mock_runner_instance_3

    # Agent 4 mock output
    mock_response_4 = MagicMock()
    mock_response_4.text = "# Custom E2E Compliance Report\nStatus: AUTO_APPROVED"
    mock_client_instance_4 = MagicMock()
    mock_client_instance_4.models.generate_content.return_value = mock_response_4
    mock_client_class_4.return_value = mock_client_instance_4

    # 2. Run the pipeline
    with patch('app.agent4_guardrail.settings') as mock_settings:
        mock_settings.GOOGLE_API_KEY = "mock_key"
        
        orchestrator = Orchestrator()
        raw_input = "Dinner with potential software clients in Tokyo, Japan. Total spent: ¥18500 JPY. Paid with corporate card by intern."
        result = orchestrator.audit_expense(raw_input)
        
        # 3. Assert results
        assert result is not None
        assert isinstance(result, dict)
        assert "receipt" in result
        assert "compliance" in result
        assert "verification" in result
        assert "report" in result
        
        # Verify specific agent outputs
        assert result["receipt"].amount == 85.50
        assert result["receipt"].country == "Italy"
        assert result["compliance"].amount_usd == 94.00
        assert result["verification"].status == "AUTO_APPROVED"
        assert "Custom E2E Compliance Report" in result["report"]
        
        # Verify sequence of executions
        mock_runner_class_1.assert_called_once()
        mock_runner_class_2.assert_called_once()
        mock_runner_class_3.assert_called_once()
        mock_client_class_4.assert_called_once_with(api_key="mock_key")
        mock_client_instance_4.models.generate_content.assert_called_once()

def test_live_demo_interactive():
    try:
        user_input = input("👉 Paste your live receipt/bill text here: ")
    except (OSError, EOFError):
        print("Stdin is not available. Skipping interactive test.")
        return

    if not user_input.strip():
        print("Error: Input text cannot be empty.")
        return
        
    PipelineOrchestrator = Orchestrator
    orchestrator = PipelineOrchestrator()
    result = orchestrator.audit_expense(user_input)
    if result and "report" in result:
        print(result["report"])
    else:
        print("Error: No report returned.")
