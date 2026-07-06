import pytest
from unittest.mock import patch, MagicMock
from app.tools import ReceiptOutput, ComplianceOutput, convert_currency
from app.agent1_parser import parse_receipt

def test_currency_conversion():
    # Test converting same currency
    assert convert_currency(100.0, "EUR", "EUR") == 100.0
    assert convert_currency(100.0, "USD", "USD") == 100.0
    
    # Test EUR -> USD conversion (using static rates: 1.10)
    assert pytest.approx(convert_currency(100.0, "EUR", "USD")) == 110.0
    
    # Test JPY -> USD conversion (using static rates: 0.0065)
    assert pytest.approx(convert_currency(10000.0, "JPY", "USD")) == 65.0
    
    # Test USD -> EUR conversion
    # USD -> USD is 100, then 100 / 1.10 = 90.9090...
    assert pytest.approx(convert_currency(110.0, "USD", "EUR"), 0.01) == 100.0

def test_parse_receipt_schemas():
    # Verify ReceiptOutput schema fields
    receipt = ReceiptOutput(amount=85.50, currency="EUR", country="Italy", has_pii=True)
    assert receipt.amount == 85.50
    assert receipt.currency == "EUR"
    assert receipt.country == "Italy"
    assert receipt.has_pii is True

    # Verify ComplianceOutput schema fields
    compliance = ComplianceOutput(
        is_compliant=True,
        amount_usd=94.00,
        policy_limit=100.00,
        excess=0.0,
        vat_reclaim=18.81
    )
    assert compliance.is_compliant is True
    assert compliance.amount_usd == 94.00
    assert compliance.policy_limit == 100.00
    assert compliance.excess == 0.0
    assert compliance.vat_reclaim == 18.81

@patch('app.agent1_parser.InMemoryRunner')
def test_parse_receipt_agent_success(mock_runner_class):
    # Mock Event object
    mock_event = MagicMock()
    mock_event.output = ReceiptOutput(amount=85.50, currency="EUR", country="Italy", has_pii=True)
    mock_event.content = None
    
    # Mock runner instance
    mock_runner_instance = MagicMock()
    mock_runner_instance.run.return_value = [mock_event]
    mock_runner_class.return_value = mock_runner_instance
    
    raw_text = "Dinner in Milan. Cost: €85.50. Card: AMEX 4532..."
    result = parse_receipt(raw_text)
    
    assert result is not None
    assert isinstance(result, ReceiptOutput)
    assert result.amount == 85.50
    assert result.currency == "EUR"
    assert result.country == "Italy"
    assert result.has_pii is True
    
    # Verify runner was instantiated and run
    mock_runner_class.assert_called_once()
    mock_runner_instance.run.assert_called_once()

@patch('app.agent1_parser.InMemoryRunner')
@patch('app.agent1_parser.anthropic.Anthropic')
def test_parse_receipt_fallback_to_claude(mock_anthropic_class, mock_runner_class):
    # Make Gemini runner fail
    mock_runner_instance = MagicMock()
    mock_runner_instance.run.side_effect = Exception("Gemini API Error")
    mock_runner_class.return_value = mock_runner_instance
    
    # Mock Anthropic Client and response
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_tool_use = MagicMock()
    mock_tool_use.type = "tool_use"
    mock_tool_use.name = "parse_receipt"
    mock_tool_use.input = {
        "amount": 120.0,
        "currency": "USD",
        "country": "United States",
        "has_pii": False
    }
    mock_response.content = [mock_tool_use]
    mock_client.messages.create.return_value = mock_response
    mock_anthropic_class.return_value = mock_client
    
    # Patch environmental API key to be present so it doesn't return None early
    with patch('os.getenv', return_value="dummy_anthropic_key"):
        result = parse_receipt("Dinner expense $120")
        
        assert result is not None
        assert isinstance(result, ReceiptOutput)
        assert result.amount == 120.0
        assert result.currency == "USD"
        assert result.country == "United States"
        assert result.has_pii is False
        
        # Verify Anthropic client was created and called with the correct model and prompt
        mock_anthropic_class.assert_called_once_with(api_key="dummy_anthropic_key")
        mock_client.messages.create.assert_called_once()
        call_kwargs = mock_client.messages.create.call_args[1]
        assert call_kwargs["model"] == "claude-3-5-sonnet-20241022"
