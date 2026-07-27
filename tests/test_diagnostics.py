"""Diagnostic redaction tests."""

from custom_components.ezviz_vacuum.diagnostics import _redact


def test_recursive_redaction() -> None:
    result = _redact(
        {
            "password": "secret",
            "nested": {
                "accessToken": "token",
                "deviceSerial": "ABC",
                "safe": 1,
            },
        }
    )
    assert result["password"] == "**REDACTED**"
    assert result["nested"]["accessToken"] == "**REDACTED**"
    assert result["nested"]["deviceSerial"] == "**REDACTED**"
    assert result["nested"]["safe"] == 1
