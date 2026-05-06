from __future__ import annotations

from fastapi import FastAPI

from .config import settings
from .routers.webhook import router as webhook_router


app = FastAPI(title=settings.app_name)
app.include_router(webhook_router)
