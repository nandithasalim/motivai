import asyncio
import json
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from guardrails import check_injection

def has_injection(values):
    # check_injection calls OpenAI (blocking), so this runs in a worker thread
    return any(check_injection(v) for v in values)


class GuardrailMiddleware(BaseHTTPMiddleware):

    PROTECTED_PATHS = ["/v1/tasks", "/v1/groups/create", "/v1/upload_reel"]

    async def dispatch(self, request: Request, call_next):
        if request.url.path in self.PROTECTED_PATHS:
            try:
                body = await request.body()
                body_text = body.decode("utf-8")
                data = json.loads(body_text)

                values = [v for v in data.values() if isinstance(v, str)]
                if await asyncio.to_thread(has_injection, values):
                    return JSONResponse(
                        {"error": "Invalid input detected"},
                        status_code=400
                    )
            except Exception:
                pass

        response = await call_next(request)
        return response