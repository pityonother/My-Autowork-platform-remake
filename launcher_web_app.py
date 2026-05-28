from __future__ import annotations

from app.factory import create_app
from app.web.launcher.routes import router as launcher_router


app = create_app("模块 Launcher", routers=[launcher_router])
