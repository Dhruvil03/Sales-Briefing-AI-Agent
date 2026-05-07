# backend/app/db.py
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base
import os

Base = declarative_base()

# Read DATABASE_URL from env; support psycopg2 -> asyncpg conversion if user forgot to update .env
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://sc:scpass@localhost:5432/salescopilot")
if DATABASE_URL.startswith("postgresql+psycopg2://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql+psycopg2://", "postgresql+asyncpg://", 1)

# Echo=False to keep logs clean
engine = create_async_engine(DATABASE_URL, echo=False, future=True, pool_pre_ping=True,
    pool_recycle=1800,)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

async def get_session() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session