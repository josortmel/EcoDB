"""Rate limiting middleware — Tarea L1-GS1 / VS9."""
from __future__ import annotations

import time
from collections import defaultdict

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from settings import RATE_LIMIT_SEARCH as SEARCH_LIMIT, RATE_LIMIT_DEFAULT as DEFAULT_LIMIT, RATE_LIMIT_WINDOW as WINDOW


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app) -> None:
        super().__init__(app)
        self.requests: dict[str, list[float]] = defaultdict(list)

    async def dispatch(self, request: Request, call_next):
        actor_id = "anon"
        auth = request.headers.get("authorization", "")
        if auth.startswith("Bearer "):
            try:
                import jwt
                payload = jwt.decode(auth[7:], options={"verify_signature": False})
                actor_id = str(payload.get("sub", "anon"))
            except Exception:
                pass

        now = time.time()
        key = f"{actor_id}:{request.url.path}"

        self.requests[key] = [t for t in self.requests[key] if now - t < WINDOW]

        limit = SEARCH_LIMIT if "/search" in request.url.path else DEFAULT_LIMIT

        if len(self.requests[key]) >= limit:
            return JSONResponse(
                status_code=429,
                content={"detail": f"rate limit exceeded: {limit} requests per {WINDOW}s", "retry_after_seconds": WINDOW},
            )

        self.requests[key].append(now)
        return await call_next(request)
