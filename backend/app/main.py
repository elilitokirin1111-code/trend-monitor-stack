"""
HotPush - 热点聚合推送平台
主入口文件
"""
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.middleware.auth import AuthMiddleware
from app.middleware.correlation import CorrelationMiddleware
from app.routers import (
    api,
    auth,
    config,
    history,
    hotspot_annotations,
    hotspot_deliveries,
    hotspot_monitoring,
    hotspot_reports,
    hotspots_v1,
    rules,
    scheduler,
    sources,
    trends,
    users,
)
from app.services.scheduler import start_scheduler, stop_scheduler
from app.utils.logger import logger

# 前端静态文件目录
FRONTEND_DIR = Path(__file__).parent.parent.parent / "frontend"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时
    logger.info("HotPush 启动中...")
    start_scheduler()
    logger.info("定时任务已启动")
    yield
    # 关闭时
    stop_scheduler()
    logger.info("HotPush 已关闭")


# 生产环境禁用 Swagger 文档
docs_url = "/docs" if settings.debug else None
redoc_url = "/redoc" if settings.debug else None

app = FastAPI(
    title="HotPush",
    description="热点聚合推送平台 - 聚合全网热点，主动推送到你指定的平台",
    version="0.5.0",
    lifespan=lifespan,
    docs_url=docs_url,
    redoc_url=redoc_url,
    openapi_url="/openapi.json" if settings.debug else None
)

# CORS 配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 认证中间件
app.add_middleware(AuthMiddleware)

# Correlation/trace ID 中间件（最先执行，为所有请求提供 X-Correlation-ID）
app.add_middleware(CorrelationMiddleware)

# 注册路由
app.include_router(api.router, prefix="/api", tags=["API"])
app.include_router(auth.router, prefix="/api/auth", tags=["Auth"])
app.include_router(config.router, prefix="/api/config", tags=["Config"])
app.include_router(sources.router, prefix="/api/sources", tags=["Sources"])
app.include_router(rules.router, prefix="/api/rules", tags=["Rules"])
app.include_router(history.router, prefix="/api/history", tags=["History"])
app.include_router(scheduler.router, prefix="/api/scheduler", tags=["Scheduler"])
app.include_router(users.router, prefix="/api/users", tags=["Users"])
app.include_router(trends.router, prefix="/api/trends", tags=["Trends"])
app.include_router(
    hotspots_v1.router,
    prefix="/api/v1/hotspots",
    tags=["Hotspot Dashboard V1"],
)
app.include_router(
    hotspot_annotations.router,
    prefix="/api/v1/hotspots",
    tags=["Hotspot Human Review and Knowledge"],
)
app.include_router(
    hotspot_reports.router,
    prefix="/api/v1/hotspots",
    tags=["Hotspot Reports V1"],
)
app.include_router(
    hotspot_deliveries.router,
    prefix="/api/v1/hotspots",
    tags=["Hotspot Deliveries V1"],
)
app.include_router(
    hotspot_monitoring.router,
    prefix="/api/v1/hotspots",
    tags=["Hotspot Monitoring V1"],
)


@app.get("/health")
async def health():
    """Liveness 健康检查"""
    return {"status": "ok"}


@app.get("/health/ready")
async def readiness():
    """就绪检查：数据库连接可用即就绪"""
    from app.services.database import db as database

    try:
        with database.get_connection() as connection:
            cursor = connection.cursor()
            cursor.execute("SELECT 1")
        return {"status": "ready", "database": "ok"}
    except Exception as exc:  # noqa: BLE001 - readiness must report, not raise
        from app.utils.logger import logger

        logger.error(f"就绪检查失败: {exc}")
        return {"status": "not_ready", "database": "unavailable"}


@app.get("/")
async def root():
    """根路径 - 返回前端页面"""
    index_file = FRONTEND_DIR / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    return {
        "name": "HotPush",
        "version": "0.5.0",
        "description": "热点聚合推送平台",
        "docs": "/docs"
    }


@app.get("/bg.jpg")
async def background_image():
    """背景图片"""
    bg_file = FRONTEND_DIR / "bg.jpg"
    if bg_file.exists():
        return FileResponse(bg_file, media_type="image/jpeg")
    raise HTTPException(status_code=404, detail="Background image not found")


@app.get("/favicon.ico")
async def favicon():
    """网站图标"""
    favicon_file = FRONTEND_DIR / "favicon.ico"
    if favicon_file.exists():
        return FileResponse(favicon_file, media_type="image/x-icon")
    raise HTTPException(status_code=404, detail="Favicon not found")


# 挂载前端静态文件（如有 CSS/JS 等资源）
if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")
