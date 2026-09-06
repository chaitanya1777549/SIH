"""
SIH26027 — AI-Powered Automatic Block Planning API
FastAPI Backend Application Entrypoint using SQLAlchemy.
"""
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.database import engine, check_db_health
from backend.schemas import HealthResponse
from backend.routes.departments import router as departments_router
from backend.routes.coa import router as coa_router
from backend.routes.emergency import router as emergency_router
from backend.routes.nl_intake import router as nl_intake_router

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("backend.main")

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifecycle management using SQLAlchemy engine.
    Verifies database connection on startup, disposes engine on shutdown.
    """
    logger.info("Starting up SIH26027 Automatic Block Planning API (SQLAlchemy)...")
    try:
        health = check_db_health()
        logger.info(f"Connected to Supabase PostgreSQL successfully: {health}")
    except Exception as e:
        logger.error(f"Failed to connect to Supabase PostgreSQL on startup: {e}")
    yield
    logger.info("Shutting down API, disposing SQLAlchemy engine...")
    engine.dispose()

app = FastAPI(
    title="SIH26027 — AI-Powered Automatic Block Planning API",
    description="SQLAlchemy-backed API for Visakhapatnam-Vijayawada corridor block planning, optimizer, and department coordination.",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS middleware for React/frontend clients
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routes
app.include_router(departments_router)
app.include_router(coa_router)
app.include_router(emergency_router)
app.include_router(nl_intake_router)


@app.get("/", tags=["Root"])
def root():
    return {
        "project": "SIH26027 — AI-Powered Automatic Block Planning",
        "corridor": "Visakhapatnam (VSKP) -> Vijayawada (BZA)",
        "orm": "SQLAlchemy 2.0",
        "status": "online",
        "docs_url": "/docs",
        "voice_tester_url": "/voice-tester",
    }

@app.get("/voice-tester", tags=["Voice Intake Tester"])
def voice_tester():
    """
    Serves the live interactive browser-based Voice Defect Intake Studio.
    Allows speaking directly into the microphone, transcribing via Whisper large-v3,
    parsing via gpt-oss-120b, and creating the defect row in Supabase.
    """
    import os
    from fastapi.responses import FileResponse
    html_path = os.path.join(os.path.dirname(__file__), "static", "voice_tester.html")
    return FileResponse(html_path)

@app.get("/health", response_model=HealthResponse, tags=["Health"])
def health_check():
    """
    Health check endpoint verifying live Supabase PostgreSQL connectivity and latency via SQLAlchemy.
    """
    db_health = check_db_health()
    return {
        "status": "healthy" if db_health["status"] == "healthy" else "degraded",
        "database": db_health,
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=True)
