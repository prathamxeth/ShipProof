from pathlib import Path
from pydantic import BaseModel, Field, model_validator
from typing import Optional, Literal
import os
import secrets
from dotenv import load_dotenv

APP_BASE_DIR = Path(__file__).resolve().parent.parent.parent
APP_WORKSPACE_DIR = APP_BASE_DIR.parent
APP_DATA_DIR = APP_BASE_DIR / "data"
APP_EVIDENCE_DIR = APP_DATA_DIR / "evidence"
APP_BACKUP_DIR = APP_DATA_DIR / "backups"

# Load .env if present
env_path = APP_WORKSPACE_DIR / ".env"
if env_path.exists():
    load_dotenv(dotenv_path=env_path)

class Settings(BaseModel):
    APP_NAME: str = Field(default="ShipProof")
    APP_VERSION: str = Field(default="0.1.0")
    DEBUG: bool = Field(default=os.getenv("DEBUG", "false").lower() == "true")
    
    # Deployment & Security Modes: "development", "trusted_single_tenant", "production"
    DEPLOYMENT_MODE: Literal["development", "trusted_single_tenant", "production"] = Field(
        default=os.getenv("DEPLOYMENT_MODE", "development")  # type: ignore
    )
    SHIPPROOF_API_KEY: Optional[str] = Field(default=os.getenv("SHIPPROOF_API_KEY"))
    SESSION_SECRET: Optional[str] = Field(default=os.getenv("SESSION_SECRET"))
    RATE_LIMIT_PER_MINUTE: int = Field(default=int(os.getenv("RATE_LIMIT_PER_MINUTE", "60")))
    
    # Paths
    BASE_DIR: Path = Field(default=APP_BASE_DIR)
    WORKSPACE_DIR: Path = Field(default=APP_WORKSPACE_DIR)
    DATA_DIR: Path = Field(default=APP_DATA_DIR)
    EVIDENCE_DIR: Path = Field(default=APP_EVIDENCE_DIR)
    BACKUP_DIR: Path = Field(default=APP_BACKUP_DIR)
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
    KANE_EGRESS_PROXY: Optional[str] = Field(default=os.getenv("KANE_EGRESS_PROXY"))
    
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
    TRUSTED_PROXIES: list[str] = Field(default=["127.0.0.1", "::1"])
    MAX_CONCURRENT_RUNS: int = Field(default=int(os.getenv("MAX_CONCURRENT_RUNS", "2")))
    
    # Worker Container & Orchestration Configuration
    WORKER_EXECUTION_MODE: Literal["container", "subprocess"] = Field(
        default=os.getenv("WORKER_EXECUTION_MODE", "container")  # type: ignore
    )
    WORKER_IMAGE: str = Field(default=os.getenv("WORKER_IMAGE", "shipproof-worker-production:latest"))
    WORKER_DOCKER_SOCKET: str = Field(default=os.getenv("DOCKER_HOST", "unix:///Users/pratham/.docker/run/docker.sock"))
    WORKER_MEMORY_LIMIT: str = Field(default="2048m")
    WORKER_CPU_LIMIT: str = Field(default="2.0")
    WORKER_PIDS_LIMIT: int = Field(default=200)
    WORKER_STARTUP_TIMEOUT_SEC: int = Field(default=15)
    WORKER_IPC_DIR: Path = Field(default=APP_DATA_DIR / "ipc")

    @model_validator(mode="after")
    def validate_deployment_security(self):
        mode = self.DEPLOYMENT_MODE

        if mode == "production":
            # 1. Must fail closed if API key is missing or trivial
            if not self.SHIPPROOF_API_KEY or len(self.SHIPPROOF_API_KEY.strip()) < 16:
                raise ValueError(
                    "Production deployment mode requires SHIPPROOF_API_KEY with at least 16 characters. Fail-closed."
                )
            # 2. Must prohibit private network/local SSRF targets in production
            if self.ALLOW_LOCAL_TARGETS:
                raise ValueError(
                    "Production deployment mode requires ALLOW_LOCAL_TARGETS=False to prevent SSRF against internal infrastructure."
                )
            # 3. Must not use wildcard CORS in production
            if "*" in self.CORS_ORIGINS or not self.CORS_ORIGINS:
                raise ValueError(
                    "Production deployment mode requires explicit CORS_ORIGINS whitelist without wildcards."
                )

        elif mode == "trusted_single_tenant":
            # If API key not explicitly set in trusted single tenant mode, generate a secure ephemeral key
            if not self.SHIPPROOF_API_KEY:
                generated = f"sp_beta_{secrets.token_hex(20)}"
                self.SHIPPROOF_API_KEY = generated
                print(f"[SECURITY] Generated ephemeral single-tenant API Key: {generated}")

        elif mode == "development":
            # Development mode defaults to allowing local targets for Sample Store
            pass

        return self

settings = Settings()

# Ensure runtime directories exist
settings.DATA_DIR.mkdir(parents=True, exist_ok=True)
settings.EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
settings.BACKUP_DIR.mkdir(parents=True, exist_ok=True)
settings.WORKER_IPC_DIR.mkdir(parents=True, exist_ok=True)
