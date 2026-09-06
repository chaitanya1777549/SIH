"""
Database connection and session management for Supabase PostgreSQL using SQLAlchemy.
"""
import os
import time
import logging
from typing import Generator, Dict, Any
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.orm import declarative_base, sessionmaker, Session

logger = logging.getLogger("backend.database")

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(ROOT_DIR, ".env"))
DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL environment variable is not set in .env")

# Configure SQLAlchemy engine with connection pool
engine = create_engine(
    DATABASE_URL,
    pool_size=5,
    max_overflow=10,
    pool_pre_ping=True,
    pool_recycle=300,
    connect_args={
        "connect_timeout": 10,
        "keepalives": 1,
        "keepalives_idle": 30,
        "keepalives_interval": 10,
        "keepalives_count": 5,
    }
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db() -> Generator[Session, None, None]:
    """
    FastAPI dependency yielding a SQLAlchemy session and closing it cleanly.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def check_db_health() -> Dict[str, Any]:
    """
    Pings the database and returns basic connectivity metrics using SQLAlchemy.
    """
    t0 = time.time()
    with engine.connect() as conn:
        res = conn.execute(text("SELECT 1 as ping")).scalar()
        stations_count = conn.execute(text("SELECT count(*) FROM stations")).scalar()
        sections_count = conn.execute(text("SELECT count(*) FROM block_sections")).scalar()
        trains_count = conn.execute(text("SELECT count(*) FROM trains")).scalar()
    duration_ms = round((time.time() - t0) * 1000, 2)
    return {
        "status": "healthy" if res == 1 else "unhealthy",
        "latency_ms": duration_ms,
        "counts": {
            "stations": stations_count,
            "block_sections": sections_count,
            "trains": trains_count
        }
    }
