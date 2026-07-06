import os
import logging
from pydantic import BaseModel, Field, field_validator, ValidationError
from dotenv import load_dotenv

# Set up logging configuration
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("ConfigLoader")

# Load variables from .env file
load_dotenv()

class AppSettings(BaseModel):
    GOOGLE_API_KEY: str = Field(..., description="Google Gemini API Key")
    FOREX_API_KEY: str = Field(..., description="Forex Exchange Rates API Key")
    ANTHROPIC_API_KEY: str | None = Field(default=None, description="Optional Anthropic backup API Key")
    ENVIRONMENT: str = Field(default="development", description="Deployment environment")
    DEBUG: bool = Field(default=True, description="Enable debug logging and mode")

    @field_validator("GOOGLE_API_KEY")
    @classmethod
    def check_google_key(cls, v: str) -> str:
        v_str = str(v).strip()
        if not v_str or v_str == "" or "your_google_api_key" in v_str:
            raise ValueError("GOOGLE_API_KEY is not configured or holds placeholder value.")
        return v_str

    @field_validator("FOREX_API_KEY")
    @classmethod
    def check_forex_key(cls, v: str) -> str:
        v_str = str(v).strip()
        if not v_str or v_str == "" or "your_forex_api_key" in v_str:
            raise ValueError("FOREX_API_KEY is not configured or holds placeholder value.")
        return v_str

# Attempt validation and log if errors are present
settings = None
try:
    raw_google_key = os.getenv("GOOGLE_API_KEY")
    raw_forex_key = os.getenv("FOREX_API_KEY")
    raw_anthropic_key = os.getenv("ANTHROPIC_API_KEY")
    raw_env = os.getenv("ENVIRONMENT", "development")
    raw_debug = os.getenv("DEBUG", "True").lower() in ("true", "1", "yes")

    config_input = {
        "GOOGLE_API_KEY": raw_google_key if raw_google_key else "",
        "FOREX_API_KEY": raw_forex_key if raw_forex_key else "",
        "ANTHROPIC_API_KEY": raw_anthropic_key if raw_anthropic_key else None,
        "ENVIRONMENT": raw_env,
        "DEBUG": raw_debug
    }

    settings = AppSettings(**config_input)
    logger.info("[OK] Configuration validated and loaded successfully.")
except ValidationError as e:
    logger.error("[ERROR] Configuration validation failed! Please check your .env file setup.")
    for error in e.errors():
        field = " -> ".join(str(loc) for loc in error["loc"])
        logger.error(f"   [Field Error] {field}: {error['msg']}")
    
    # Fallback settings to avoid crashing imports with AttributeError
    fallback_input = {
        "GOOGLE_API_KEY": "MISSING",
        "FOREX_API_KEY": "MISSING",
        "ANTHROPIC_API_KEY": None,
        "ENVIRONMENT": "development",
        "DEBUG": True
    }
    settings = AppSettings.model_construct(**fallback_input)
