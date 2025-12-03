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
    """啟動 PCBA 測試流程：呼叫 C 程式執行所有測項，解析 JSON 輸出並廣播事件給前端。
    
    流程：
    1. 接收 serial (UID)
    2. 依序執行 C 程式測試每個階段：wifi, firmware, touch, bluetooth, speaker
    3. 解析 C 程式輸出的 JSON
    4. 廣播 testing 和最終結果 (pass/fail) 事件給前端
    """
    serial = (request.serial or "").strip()
    if not serial:
        raise HTTPException(status_code=400, detail="serial is required")

    logger.info(f"[PCBA:/start-test] Starting test for serial: {serial}")

    # C 程式路徑（假設已編譯在 /app/tester/pcba_demo）
    c_program = os.environ.get("PCBA_TESTER_PATH", "/app/tester/pcba_demo")
    
    if not os.path.exists(c_program):
        logger.error(f"[PCBA:/start-test] C program not found: {c_program}")
        raise HTTPException(status_code=500, detail="PCBA tester program not found")

    stages = ["wifi", "firmware", "touch", "bluetooth", "speaker"]
    
    try:
        for stage in stages:
            # 先廣播 testing 狀態
            testing_msg = {
                "type": "pcba_event",
                "data": {
                    "serial": serial,
                    "stage": stage,
                    "status": "testing",
                },
                "timestamp": datetime.now().isoformat(),
            }
            await manager.broadcast(testing_msg)
            logger.info(f"[PCBA:/start-test] Broadcasting testing for {stage}")

            # 執行 C 程式
            result = subprocess.run(
                [c_program, stage, serial],
                capture_output=True,
                text=True,
                timeout=10
            )

            if result.returncode != 0:
                logger.error(f"[PCBA:/start-test] Stage {stage} failed with return code {result.returncode}")
                # 廣播 fail 事件
                fail_msg = {
                    "type": "pcba_event",
                    "data": {
                        "serial": serial,
                        "stage": stage,
                        "status": "fail",
                        "detail": {"error": "test execution failed"},
                    },
                    "timestamp": datetime.now().isoformat(),
                }
                await manager.broadcast(fail_msg)
                continue

            # 解析 JSON 輸出
            try:
                output = result.stdout.strip()
                event_data = json.loads(output)
                
                # 廣播最終結果
                result_msg = {
                    "type": "pcba_event",
                    "data": event_data,
                    "timestamp": datetime.now().isoformat(),
                }
                await manager.broadcast(result_msg)
                logger.info(f"[PCBA:/start-test] Stage {stage} completed: {event_data.get('status')}")
                
            except json.JSONDecodeError as e:
                logger.error(f"[PCBA:/start-test] Failed to parse JSON from stage {stage}: {e}")
                fail_msg = {
                    "type": "pcba_event",
                    "data": {
                        "serial": serial,
                        "stage": stage,
                        "status": "fail",
                        "detail": {"error": "invalid test output"},
                    },
                    "timestamp": datetime.now().isoformat(),
                }
                await manager.broadcast(fail_msg)

        logger.info(f"[PCBA:/start-test] All stages completed for serial: {serial}")
        return {"status": "completed", "serial": serial, "stages": stages}

    except subprocess.TimeoutExpired:
        logger.error(f"[PCBA:/start-test] Test timeout for serial: {serial}")
        raise HTTPException(status_code=500, detail="Test execution timeout")
    except Exception as e:
        logger.exception(f"[PCBA:/start-test] Unexpected error: {e}")
        raise HTTPException(status_code=500, detail=f"Test execution error: {str(e)}")

