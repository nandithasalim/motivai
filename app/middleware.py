import json
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from guardrails import check_injection

class GuardrailMiddleware(BaseHTTPMiddleware):
    
    PROTECTED_PATHS = ["/v1/tasks", "/v1/groups/create", "/v1/upload_reel"]
    
    async def dispatch(self, request: Request, call_next):
        if request.url.path in self.PROTECTED_PATHS:
            try:
                body = await request.body()
                body_text = body.decode("utf-8")
                data = json.loads(body_text)
                
                for value in data.values():
                    if isinstance(value, str) and check_injection(value):
                        return JSONResponse(
                            {"error": "Invalid input detected"},
                            status_code=400
                        )
            except Exception:
                pass
        
        response = await call_next(request)
        return response