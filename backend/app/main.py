from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from app.config import settings
from app.database import init_db
from app.routers import test_records, websocket
from app.routers import cloud_status, firmware_flashes, pcba_events, sensor_events
from app.scheduler import start_scheduler, stop_scheduler
from app.sensor_watcher_manager import start_sensor_watcher, stop_sensor_watcher


@asynccontextmanager
async def lifespan(app: FastAPI):
    """應用程式生命週期管理"""
    # 啟動時執行
    print("Starting up...")
    init_db()  # 初始化資料庫
    start_scheduler()  # 啟動排程器
    if settings.AUTO_START_SENSOR_WATCHER:
        await start_sensor_watcher()
    else:
        print("Automatic sensor_watcher startup is disabled")
    try:
        yield
    finally:
        # 關閉時只停止由這個 Backend 啟動的 watcher。
        print("Shutting down...")
        await stop_sensor_watcher()
        stop_scheduler()  # 停止排程器


app = FastAPI(
    title="Production Test System API",
    description="生產測試資料管理系統 API",
    version="1.0.0",
    lifespan=lifespan
)

# CORS 設定
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_origin_regex=settings.CORS_ORIGIN_REGEX,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 註冊路由
app.include_router(test_records.router)
app.include_router(websocket.router)
app.include_router(pcba_events.router)
app.include_router(sensor_events.router)
app.include_router(cloud_status.router)
app.include_router(firmware_flashes.router)


@app.get("/")
async def root():
    return {
        "message": "Production Test System API",
        "version": "1.0.0",
        "docs": "/docs"
    }


@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "cloud_upload_enabled": settings.CLOUD_UPLOAD_ENABLED
    }
