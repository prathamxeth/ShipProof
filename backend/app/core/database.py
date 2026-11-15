from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import text
from backend.app.core.config import settings
from backend.app.core.logging import get_logger
from backend.app.models.entities import Base

logger = get_logger("database")

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    connect_args={"check_same_thread": False} if "sqlite" in settings.DATABASE_URL else {},
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)

async def init_db() -> None:
    logger.info(f"Initializing database at {settings.DATABASE_URL}...")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        
        # Check and migrate columns on verification_runs and repair_records if needed
        if "sqlite" in settings.DATABASE_URL:
            # verification_runs
            result = await conn.execute(text("PRAGMA table_info(verification_runs);"))
            existing_cols = {row[1] for row in result.fetchall()}
            if "exit_code" not in existing_cols:
                await conn.execute(text("ALTER TABLE verification_runs ADD COLUMN exit_code INTEGER;"))
            if "raw_stdout_path" not in existing_cols:
                await conn.execute(text("ALTER TABLE verification_runs ADD COLUMN raw_stdout_path VARCHAR(1024);"))
            if "raw_stderr_path" not in existing_cols:
                await conn.execute(text("ALTER TABLE verification_runs ADD COLUMN raw_stderr_path VARCHAR(1024);"))
                
            # repair_records
            result_rep = await conn.execute(text("PRAGMA table_info(repair_records);"))
            existing_rep_cols = {row[1] for row in result_rep.fetchall()}
            new_rep_cols = {
                "git_commit_before": "VARCHAR(64)",
                "git_commit_after": "VARCHAR(64)",
                "repair_packet_json": "TEXT",
                "retest_passed": "BOOLEAN DEFAULT 0",
                "failure_notes": "TEXT",
                "updated_at": "DATETIME",
                "completed_at": "DATETIME"
            }
            for col_name, col_type in new_rep_cols.items():
                if col_name not in existing_rep_cols:
                    await conn.execute(text(f"ALTER TABLE repair_records ADD COLUMN {col_name} {col_type};"))

    logger.info("Database tables and columns verified/created successfully.")

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
