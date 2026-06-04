from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from loguru import logger
import sys
import os
from dotenv import load_dotenv

load_dotenv()

from app.core.config import settings
from app.api.routes import auth, documents
from app.middleware.logging_middleware import LoggingMiddleware

logger.remove()
logger.add(sys.stdout, format="{time:HH:mm:ss} | {level} | {message}", level="DEBUG", colorize=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"Starting {settings.app_name} v{settings.app_version}")
    logger.info(f"AI ready: {settings.ai_ready}")
    logger.info(f"Port: {settings.port}")
    yield
    logger.info("Shutdown complete")


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    lifespan=lifespan
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(LoggingMiddleware)


@app.exception_handler(RequestValidationError)
async def validation_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={"error": "Validation failed", "detail": str(exc.errors())}
    )


@app.exception_handler(Exception)
async def global_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled error: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error"}
    )


@app.get("/")
async def root():
    return {
        "service": settings.app_name,
        "version": settings.app_version,
        "status": "running",
        "ai_powered": settings.ai_ready
    }


@app.get("/health")
async def health():
    return {"status": "ok"}


app.include_router(auth.router, prefix="/api/v1")
app.include_router(documents.router, prefix="/api/v1")