import pytest
from pydantic import ValidationError

from roomloop.config.env import (
    EnvConfig,
    format_validation_error,
    load_and_validate_env,
)


def test_default_env_config():
    """Verifies default values are correctly assigned when no env vars are passed"""
    config = EnvConfig.model_validate({})
    assert config.PORT == 8000
    assert config.HOST == "localhost"
    assert config.ENVIRONMENT == "development"
    assert config.LOG_LEVEL == "INFO"


def test_valid_custom_env_config():
    """Verifies custom string values are parsed and coerced into correct types"""
    data = {
        "PORT": "8095",
        "HOST": "0.0.0.0",
        "ENVIRONMENT": "production",
        "LOG_LEVEL": "DEBUG",
    }
    config = EnvConfig.model_validate(data)
    assert config.PORT == 8095
    assert config.HOST == "0.0.0.0"
    assert config.ENVIRONMENT == "production"
    assert config.LOG_LEVEL == "DEBUG"


def test_immutability_frozen():
    """Verifies that config fields cannot be mutated at runtime"""
    config = EnvConfig.model_validate({})
    with pytest.raises(ValidationError):
        # frozen=True disallows direct attribute mutation
        config.PORT = 9999


@pytest.mark.parametrize(
    "field, invalid_value, expected_error",
    [
        ("PORT", 0, "greater than or equal to 1"),
        ("PORT", 65536, "less than or equal to 65535"),
        ("PORT", "not_a_number", "valid integer"),
        ("HOST", "", "at least 1 character"),
        ("ENVIRONMENT", "staging", "Input should be 'production'"),
        ("LOG_LEVEL", "VERBOSE", "Input should be 'DEBUG'"),
    ],
)
def test_validation_boundaries(field: str, invalid_value, expected_error: str):
    """Verifies invalid boundary inputs raise validation errors with clear messages"""
    with pytest.raises(ValidationError) as exc_info:
        EnvConfig.model_validate({field: invalid_value})
    error_text = format_validation_error(exc_info.value)
    assert field in error_text
    assert expected_error in error_text


def test_load_and_validate_env_exits_on_error(monkeypatch, capsys):
    """Verifies that invalid environment causes a clean stderr tree print and sys.exit(1)"""
    # intercept sys.exit so pytest can assert the exit code
    monkeypatch.setattr(
        "sys.exit",
        lambda code: (_ for _ in ()).throw(SystemExit(code)),
    )

    with pytest.raises(SystemExit) as exc_info:
        load_and_validate_env({"PORT": "-1"})

    assert exc_info.value.code == 1

    # capture stderr output and verify formatting
    captured = capsys.readouterr()
    assert "Invalid environment variables:" in captured.err
    assert "PORT" in captured.err
