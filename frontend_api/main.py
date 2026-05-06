from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware

from .core.config import settings
from .routers.auth import router as auth_router
from .routers.assistant import router as assistant_router
from .routers.dashboard import router as dashboard_router
from .routers.debug import router as debug_router
from .routers.knowledge import router as knowledge_router
from .routers.rag import router as rag_router
from .routers.report import router as report_router


app = FastAPI(title=settings.app_name)

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(dict.fromkeys(settings.allowed_origins + (settings.frontend_origin,))),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(SessionMiddleware, secret_key=settings.secret_key, same_site="lax")


def _health_payload():
    return {"success": True, "data": {"status": "ok"}, "message": "frontend_api is healthy"}


@app.get("/health")
def health():
    return _health_payload()


@app.get("/api/health")
def api_health():
    return _health_payload()


app.include_router(auth_router)
app.include_router(assistant_router)
app.include_router(dashboard_router)
app.include_router(debug_router)
app.include_router(knowledge_router)
app.include_router(rag_router)
app.include_router(report_router)
