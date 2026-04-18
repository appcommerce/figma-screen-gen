from pathlib import Path

from pipeline.src.naming_contract import NamingContract


def test_valid_name_parsing() -> None:
    contract = NamingContract(Path("pipeline/config/node-mapping.yaml"))
    parsed = contract.parse("component/checkbox/termsAccepted#outlined@checked!primary", "n1")
    assert parsed.level == "component"
    assert parsed.component == "checkbox"
    assert parsed.semantic_name == "termsAccepted"
    assert parsed.variant == "outlined"
    assert parsed.state == "checked"
    assert parsed.role == "primary"
    assert parsed.valid is True


def test_invalid_name_goes_to_raw_frame() -> None:
    contract = NamingContract(Path("pipeline/config/node-mapping.yaml"))
    parsed = contract.parse("Checkbox Terms Accepted", "n2")
    assert parsed.level == "raw"
    assert parsed.component == "frame"
    assert parsed.valid is False
    assert parsed.issues
