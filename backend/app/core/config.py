from pathlib import Path
from pydantic import BaseModel, Field
import os
from dotenv import load_dotenv

APP_BASE_DIR = Path(__file__).resolve().parent.parent.parent
APP_WORKSPACE_DIR = APP_BASE_DIR.parent
APP_DATA_DIR = APP_BASE_DIR / "data"
APP_EVIDENCE_DIR = APP_DATA_DIR / "evidence"

# Load .env if present
env_path = APP_WORKSPACE_DIR / ".env"
if env_path.exists():
    load_dotenv(dotenv_path=env_path)

class Settings(BaseModel):
    APP_NAME: str = Field(default="ShipProof")
    APP_VERSION: str = Field(default="0.1.0")
    DEBUG: bool = Field(default=os.getenv("DEBUG", "false").lower() == "true")
    
    # Paths
    BASE_DIR: Path = Field(default=APP_BASE_DIR)
    WORKSPACE_DIR: Path = Field(default=APP_WORKSPACE_DIR)
    DATA_DIR: Path = Field(default=APP_DATA_DIR)
    EVIDENCE_DIR: Path = Field(default=APP_EVIDENCE_DIR)
    DATABASE_URL: str = Field(
        default=os.getenv(
            "DATABASE_URL",
            f"sqlite+aiosqlite:///{APP_DATA_DIR / 'shipproof.db'}"
        )
    )
    
    # Kane CLI Configuration
    KANE_CLI_PATH: str = Field(default=os.getenv("KANE_CLI_PATH", "/opt/homebrew/bin/kane-cli"))
    KANE_CLI_USER_AGENT: str = Field(default="shipproof-antigravity")
    KANE_DEFAULT_TIMEOUT: int = Field(default=int(os.getenv("KANE_DEFAULT_TIMEOUT", "120")))
    
    # Antigravity CLI Configuration
    AGY_CLI_PATH: str = Field(default=os.getenv("AGY_CLI_PATH", "/Users/pratham/.gemini/bin/agy"))
    AGY_DEFAULT_MODEL: str = Field(default=os.getenv("AGY_DEFAULT_MODEL", "gemini-3.8-flash-high"))
    
    # Server Configuration
    HOST: str = Field(default=os.getenv("HOST", "127.0.0.1"))
    PORT: int = Field(default=int(os.getenv("PORT", "8000")))
    ENVIRONMENT: str = Field(default=os.getenv("ENVIRONMENT", "development"))
    ALLOW_LOCAL_TARGETS: bool = Field(
        default=os.getenv("ALLOW_LOCAL_TARGETS", "true").lower() == "true"
    )
    CORS_ORIGINS: list[str] = Field(default=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ])

settings = Settings()

# Ensure runtime directories exist
settings.DATA_DIR.mkdir(parents=True, exist_ok=True)
settings.EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
