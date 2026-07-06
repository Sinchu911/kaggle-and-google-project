import pytest
from app.mcp_server import PolicyEngine

def test_policy_lookup_success():
    engine = PolicyEngine(data_dir="data")
    
    # Test US lookup (direct and alias)
    us_policy = engine.lookup_policy("United States")
    assert us_policy is not None
    assert us_policy["country"] == "United States"
    assert us_policy["currency"] == "USD"
    assert us_policy["vat_rate"] == 0.0
    assert us_policy["dinner_limit"] == 150.0
    assert us_policy["lodging_limit"] == 300.0
    assert us_policy["region"] == "US"
    
    us_alias = engine.lookup_policy("US")
    assert us_alias is not None
    assert us_alias["country"] == "United States"

    # Test Italy lookup
    italy_policy = engine.lookup_policy("Italy")
    assert italy_policy is not None
    assert italy_policy["country"] == "Italy"
    assert italy_policy["currency"] == "EUR"
    assert italy_policy["vat_rate"] == 0.22
    assert italy_policy["dinner_limit"] == 100.0
    assert italy_policy["lodging_limit"] == 250.0
    assert italy_policy["region"] == "EU"

    # Test Germany lookup
    germany_policy = engine.lookup_policy("Germany")
    assert germany_policy is not None
    assert germany_policy["country"] == "Germany"
    assert germany_policy["currency"] == "EUR"
    assert germany_policy["vat_rate"] == 0.19
    assert germany_policy["dinner_limit"] == 120.0
    assert germany_policy["lodging_limit"] == 300.0
    assert germany_policy["region"] == "EU"

    # Test Japan lookup
    japan_policy = engine.lookup_policy("Japan")
    assert japan_policy is not None
    assert japan_policy["country"] == "Japan"
    assert japan_policy["currency"] == "JPY"
    assert japan_policy["vat_rate"] == 0.10
    assert japan_policy["dinner_limit"] == 20000.0
    assert japan_policy["lodging_limit"] == 35000.0
    assert japan_policy["region"] == "APAC"

    # Test Australia lookup
    australia_policy = engine.lookup_policy("Australia")
    assert australia_policy is not None
    assert australia_policy["country"] == "Australia"
    assert australia_policy["currency"] == "AUD"
    assert australia_policy["vat_rate"] == 0.10
    assert australia_policy["dinner_limit"] == 180.0
    assert australia_policy["lodging_limit"] == 320.0
    assert australia_policy["region"] == "APAC"

def test_policy_lookup_not_found():
    engine = PolicyEngine(data_dir="data")
    assert engine.lookup_policy("NonExistentCountry") is None
    assert engine.lookup_policy("") is None
    assert engine.lookup_policy(None) is None
