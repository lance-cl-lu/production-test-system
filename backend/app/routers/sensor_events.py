from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, Dict, Any, Literal
from app.routers.websocket import manager
import logging
import os

router = APIRouter(prefix="/api/sensor", tags=["Sensor Events"])
logger = logging.getLogger("uvicorn.error") or logging.getLogger(__name__)

# 和 pcba_events.py 類似的結構，但針對 Sensor
SHARED_FILE_PATH = "../shared/sensor_test.txt"


class SensorEvent(BaseModel):
    serial: str
    stage: Literal[
        "getUUID",
        "getHumidity",
        "getTemperature",
        "getPressure",
        "testLeak",
        "testButton",
        "testLED",
    ]
    status: Literal["pending", "testing", "pass", "fail"]
    progress: Optional[int] = Field(default=None, ge=0, le=100)
    detail: Optional[Dict[str, Any]] = None
    timestamp: Optional[datetime] = None


class StartTestRequest(BaseModel):
    serial: str


class SerialFoundRequest(BaseModel):
    serial_wle: str
    serial_wba: Optional[str] = None


@router.post("/read-serial")
async def read_sensor_serial():
    """
    請 sensor_watcher 從裝置讀取序號：寫入 SEARCH 指令到共享檔案。
    結果由 watcher POST 回 /serial-found，再廣播給前端。
    """
    logger.info("[Sensor:/read-serial] Read serial request received")

    try:
        with open(SHARED_FILE_PATH, "w") as f:
            f.write(f"SEARCH\n{datetime.now().isoformat()}\n")

        logger.info(f"[Sensor:/read-serial] Written SEARCH command to {SHARED_FILE_PATH}")

        return {
            "status": "searching",
            "message": "Read serial request sent to sensor_watcher.",
        }

    except Exception as e:
        logger.exception(f"[Sensor:/read-serial] Failed to write search command: {e}")
        raise HTTPException(status_code=500, detail="Failed to trigger serial read")


@router.post("/serial-found")
async def sensor_serial_found(request: SerialFoundRequest):
    """
    sensor_watcher 回報從裝置讀到的 WLE / WBA 序號，廣播給前端自動填入。
    """
    serial_wle = (request.serial_wle or "").strip()
    serial_wba = (request.serial_wba or "").strip()

    if not serial_wle:
        raise HTTPException(status_code=400, detail="serial_wle is required")

    logger.info(
        f"[Sensor:/serial-found] Received serials: WLE={serial_wle} WBA={serial_wba}"
    )

    try:
        await manager.broadcast({
            "type": "sensor_serial_found",
            "data": {"serial_wle": serial_wle, "serial_wba": serial_wba},
            "timestamp": datetime.now().isoformat(),
        })

        return {"status": "accepted", "serial_wle": serial_wle, "serial_wba": serial_wba}

    except Exception as e:
        logger.exception(f"[Sensor:/serial-found] Failed to broadcast serials: {e}")
        raise HTTPException(status_code=500, detail="Failed to broadcast serials")


@router.post("/start-test")
async def start_sensor_test(request: StartTestRequest):
    """
    啟動 Sensor 測試流程：將指令寫入共享檔案，通知外部 C 程式開始。
    """
    serial = (request.serial or "").strip()
    if not serial:
        raise HTTPException(status_code=400, detail="serial is required")

    logger.info(f"[Sensor:/start-test] Starting test for serial: {serial}")

    try:
        # 確保 shared 目錄存在
        os.makedirs(os.path.dirname(SHARED_FILE_PATH), exist_ok=True)
        # 寫入 TEST 指令和序號到共享檔案
        with open(SHARED_FILE_PATH, "w") as f:
            f.write(f"TEST {serial}\n{datetime.now().isoformat()}\n")

        logger.info(
            f"[Sensor:/start-test] Written TEST command to {SHARED_FILE_PATH}: {serial}"
        )

        return {
            "status": "triggered",
            "serial": serial,
            "message": "Test request sent to sensor_watcher. Results will be broadcasted.",
        }

    except Exception as e:
        logger.exception(f"[Sensor:/start-test] Failed to write test command: {e}")
        raise HTTPException(status_code=500, detail="Failed to trigger test")


@router.post("/events")
async def receive_sensor_event(event: SensorEvent):
    """
    接收來自 C 程式的 Sensor 事件，並透過 WebSocket 廣播給前端。
    """
    serial = (event.serial or "").strip()
    stage = (event.stage or "").strip()
    status = (event.status or "").strip()

    if not all([serial, stage, status]):
        raise HTTPException(status_code=400, detail="serial, stage, and status are required")

    logger.info(
        "[Sensor:/events] Received event",
        extra={"serial": serial, "stage": stage, "status": status, "detail": event.detail},
    )

    try:
        # 建立 WebSocket 訊息
        message = {
            "type": "sensor_event",  # 使用專屬的事件類型
            "data": {
                "serial": serial,
                "stage": stage,
                "status": status,
                "detail": event.detail,
                "progress": event.progress,
            },
            "timestamp": datetime.now().isoformat(),
        }

        await manager.broadcast(message)
        logger.info(
            "[Sensor:/events] Broadcasted event",
            extra={"serial": serial, "stage": stage, "status": status},
        )

        return {"status": "accepted"}

    except Exception as e:
        logger.exception(f"[Sensor:/events] Failed to broadcast event: {e}")
        raise HTTPException(status_code=500, detail="Failed to broadcast event")