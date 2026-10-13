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

    PROTECTED_PATHS = ["/v1/tasks", "/v1/groups/create"]

    async def dispatch(self, request: Request, call_next):
        if request.url.path in self.PROTECTED_PATHS:
            body = await request.body()
            try:
                data = json.loads(body.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                data = None   # not JSON: nothing to check here (FastAPI will validate it)

            if isinstance(data, dict):
                values = []
                for v in data.values():
                    if isinstance(v, str):
                        values.append(v)
                    elif isinstance(v, list):
                        values.extend(x for x in v if isinstance(x, str))
                if await asyncio.to_thread(has_injection, values):
                    return JSONResponse(
                        {"error": "Invalid input detected"},
                        status_code=400
                    )

        response = await call_next(request)
        return response