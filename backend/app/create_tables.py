import asyncio
from pathlib import Path
from dotenv import load_dotenv

# Load .env for local dev; on Railway env vars are injected directly so this is a no-op
env_path = Path(__file__).resolve().parents[1] / ".env"
load_dotenv(dotenv_path=env_path, override=False)

from .db import engine, Base  # import AFTER loading env
from . import models  # noqa: F401 — registers all tables with Base.metadata

async def create_all():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("Tables created")

if __name__ == "__main__":
    asyncio.run(create_all())