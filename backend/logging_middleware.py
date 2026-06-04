import time
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from loguru import logger


class LoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start = time.time()
        logger.info(f"-> {request.method} {request.url.path}")
        response = await call_next(request)
        duration = round((time.time() - start) * 1000, 1)
        level = "info" if response.status_code < 400 else "warning"
        getattr(logger, level)(
            f"<- {request.method} {request.url.path} -> {response.status_code} ({duration}ms)"
        )
        return response
