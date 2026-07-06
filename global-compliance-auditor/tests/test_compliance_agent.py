import pytest
from unittest.mock import patch, MagicMock
from app.tools import ReceiptOutput, ComplianceOutput
from app.agent2_compliance import lookup_policy_tool, convert_currency_tool, enforce_compliance

def test_lookup_policy_tool():
    # Test valid lookup
    res_italy = lookup_policy_tool("Italy")
    assert res_italy is not None
    assert res_italy["country"] == "Italy"
    assert res_italy["currency"] == "EUR"
    assert res_italy["dinner_limit"] == 100.0

    # Test fallback
    res_missing = lookup_policy_tool("Atlantis")
    assert res_missing["region"] == "GLOBAL"
    assert res_missing["dinner_limit"] == 100.0

def test_convert_currency_tool():
    # EUR -> USD static rate is 1.10
    assert pytest.approx(convert_currency_tool(100.0, "EUR", "USD")) == 110.0
    # Same currency
    assert convert_currency_tool(100.0, "USD", "USD") == 100.0

@patch('app.agent2_compliance.InMemoryRunner')
def test_enforce_compliance_agent_success(mock_runner_class):
    # Mock Event object
    mock_event = MagicMock()
    mock_event.output = ComplianceOutput(
        is_compliant=True,
        amount_usd=94.00,
        policy_limit=110.00,  # 100 EUR = 110 USD limit
        excess=0.0,
        vat_reclaim=18.81
    )
    
    # Mock runner instance
    mock_runner_instance = MagicMock()
    mock_runner_instance.run.return_value = [mock_event]
    mock_runner_class.return_value = mock_runner_instance
    
    receipt = ReceiptOutput(amount=85.50, currency="EUR", country="Italy", has_pii=True)
    result = enforce_compliance(receipt)
    
    assert result is not None
    assert isinstance(result, ComplianceOutput)
    assert result.is_compliant is True
    assert result.amount_usd == 94.00
    assert result.policy_limit == 110.00
    assert result.excess == 0.0
    assert result.vat_reclaim == 18.81
    
    # Verify runner was instantiated and run
    mock_runner_class.assert_called_once()
    mock_runner_instance.run.assert_called_once()

@patch('app.agent2_compliance.InMemoryRunner')
def test_enforce_compliance_fallback_to_local_report(mock_runner_class):
    # Make Gemini runner fail
    mock_runner_instance = MagicMock()
    mock_runner_instance.run.side_effect = Exception("Gemini API Error")
    mock_runner_class.return_value = mock_runner_instance
    
    receipt = ReceiptOutput(amount=85.50, currency="EUR", country="Italy", has_pii=True)
    
    result = enforce_compliance(receipt)
    
    assert result is not None
    assert "Global Compliance Audit Report" in result
