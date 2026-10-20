import os
import sys
from typing import Literal

from dotenv import load_dotenv
from pydantic import BaseModel, Field, ValidationError

load_dotenv("./config/.env")


class EnvConfig(BaseModel):
    """Runtime Environment Configuration"""

    model_config = {"extra": "ignore", "frozen": True, "validate_assignment": True}

    PORT: int = Field(
        default=8000, ge=1, le=65535, description="Port number for REST service"
    )

    HOST: str = Field(
        default="localhost",
        min_length=1,
        description="Network host interface to bind the REST service",
    )

    ENVIRONMENT: Literal["production", "development", "test"] = Field(
        default="development", description="Active runtime environment mode"
    )

    LOG_LEVEL: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = Field(
        default="INFO", description="Logging level"
    )


def format_validation_error(err: ValidationError) -> str:
    """Formats pydantic validation error into tree format"""
    lines = ["Invalid environment variables:"]
    for error in err.errors():
        field_path = " -> ".join(str(elem) for elem in error.get("loc"))
        message = error.get("msg")
        input_val = error.get("input")
        lines.append(f" - {field_path}: {message} (recieved: {input_val!r})")
    return "\n".join(lines)


def load_and_validate_env(source: dict[str, str] | None = None) -> EnvConfig:
    """Validates environment variables at application boot and exits on error"""
    raw_data = os.environ if source is None else source
    try:
        return EnvConfig.model_validate(raw_data)
    except ValidationError as err:
        sys.stderr.write(format_validation_error(err) + "\n")
        sys.exit(1)


env: EnvConfig = load_and_validate_env(os.environ)
