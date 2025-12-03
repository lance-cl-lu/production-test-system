from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, Dict, Any
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import TestRecord
from app.routers.websocket import manager
import logging
import subprocess
import json
import os

router = APIRouter(prefix="/api/pcba", tags=["PCBA Events"])
logger = logging.getLogger("uvicorn.error") or logging.getLogger(__name__)


class PcbaEvent(BaseModel):
    serial: str
    stage: str  # wifi | firmware | touch | bluetooth | speaker
    status: str  # pending | testing | pass | fail
    progress: Optional[int] = Field(default=None, ge=0, le=100)
    detail: Optional[Dict[str, Any]] = None
    timestamp: Optional[datetime] = None


@router.post("/events")
async def receive_pcba_event(
    event: PcbaEvent,
    request: Request,
    db: Session = Depends(get_db),
):
    """接收來自本機 C 程式的 PCBA 事件，並透過 WebSocket 廣播給前端。

    增加詳細的伺服器端日誌與容錯：
    - 記錄 client IP、headers、payload、解析後欄位
    - 驗證必要欄位與值域
    - 失敗時回傳 400，成功廣播則回傳 202 accepted
    """

    client_ip = request.client.host if request.client else "unknown"
    headers = dict(request.headers)

    try:
        logger.info(
            "[PCBA:/events] incoming payload",
            extra={
                "client_ip": client_ip,
                "headers": {k: headers.get(k) for k in ["content-type", "user-agent"]},
                "payload": event.model_dump(),
            },
        )

        # 基本驗證與正規化
        serial = (event.serial or "").strip()
        stage = (event.stage or "").strip().lower()
        status = (event.status or "").strip().lower()

        if not serial:
            logger.warning("[PCBA:/events] missing serial", extra={"payload": event.model_dump()})
            raise HTTPException(status_code=400, detail="serial is required")

        valid_stages = {"wifi", "firmware", "touch", "bluetooth", "speaker"}
        valid_status = {"pending", "testing", "pass", "fail"}

        if stage not in valid_stages:
            logger.warning("[PCBA:/events] invalid stage", extra={"stage": stage})
            raise HTTPException(status_code=400, detail=f"invalid stage: {stage}")
        if status not in valid_status:
            logger.warning("[PCBA:/events] invalid status", extra={"status": status})
            raise HTTPException(status_code=400, detail=f"invalid status: {status}")

        # 將 payload 的 timestamp 轉為 ISO 字串，避免 datetime 無法序列化
        payload = event.model_dump()
        if isinstance(payload.get("timestamp"), datetime):
            payload["timestamp"] = payload["timestamp"].isoformat()

        message = {
            "type": "pcba_event",
            "data": {
                **payload,
                "serial": serial,  # 使用修剪後的值
                "stage": stage,
                "status": status,
            },
            "timestamp": datetime.now().isoformat(),
        }

        await manager.broadcast(message)
        logger.info(
            "[PCBA:/events] broadcasted",
            extra={"serial": serial, "stage": stage, "status": status},
        )
        # 202: accepted for async processing
        return {"status": "accepted", "serial": serial, "stage": stage, "state": status}

    except HTTPException:
        # 已記錄詳細資訊，上拋讓 FastAPI 回傳對應錯誤碼
        raise
    except Exception as e:
        logger.exception("[PCBA:/events] unhandled error")
        raise HTTPException(status_code=500, detail="internal error")


@router.post("/debug-broadcast")
async def debug_broadcast(serial: str = "NL20231203001"):
    """測試廣播一則 pcba_event 給前端，用於驗證 WS 連線與前端接收。"""
    message = {
        "type": "pcba_event",
        "data": {
            "serial": serial,
            "stage": "wifi",
            "status": "testing",
            "detail": {"rssi": -50},
        },
        "timestamp": datetime.now().isoformat(),
    }
    await manager.broadcast(message)
    return {"status": "broadcasted", "serial": serial}


class StartTestRequest(BaseModel):
    serial: str


@router.post("/start-test")
async def start_test(request: StartTestRequest, db: Session = Depends(get_db)):
    """啟動 PCBA 測試流程：將 UID 寫入共享檔案，通知 Mac 上的 C 程式開始測試。
    
    流程：
    1. 接收 serial (UID)
    2. 寫入 UID 到 /shared/pcba_test.txt
    3. Mac 上的 C 程式監看檔案變化，自動執行測試
    4. C 程式 POST 結果到 /api/pcba/events，透過 WebSocket 廣播給前端
    """
    serial = (request.serial or "").strip()
    if not serial:
        raise HTTPException(status_code=400, detail="serial is required")

    logger.info(f"[PCBA:/start-test] Starting test for serial: {serial}")

    try:
        # 寫入 UID 到共享檔案
        shared_file = "/shared/pcba_test.txt"
        with open(shared_file, "w") as f:
            f.write(f"{serial}\n{datetime.now().isoformat()}\n")
        
        logger.info(f"[PCBA:/start-test] Written UID to {shared_file}: {serial}")
        
        return {
            "status": "triggered",
            "serial": serial,
            "message": "Test request sent to local C program. Results will be broadcasted via WebSocket.",
        }
        
    except Exception as e:
        logger.exception(f"[PCBA:/start-test] Failed to write shared file: {e}")
        raise HTTPException(status_code=500, detail="Failed to trigger test")

