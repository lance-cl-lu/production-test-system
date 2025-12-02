from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from app.config import settings
from app.database import init_db
from app.routers import test_records, websocket
from app.scheduler import start_scheduler, stop_scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    """應用程式生命週期管理"""
    # 啟動時執行
    print("Starting up...")
    init_db()  # 初始化資料庫
    start_scheduler()  # 啟動排程器
    yield
    # 關閉時執行
    print("Shutting down...")
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
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 註冊路由
app.include_router(test_records.router)
app.include_router(websocket.router)


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
