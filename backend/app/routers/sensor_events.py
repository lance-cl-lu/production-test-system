from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, selectinload
from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, Dict, Any, Literal, List
from app.routers.websocket import manager
from app.database import get_db
from app.models import SensorTestRun, SensorTestItem
from app.schemas import SensorTestRunResponse
import json
import logging
import os

router = APIRouter(prefix="/api/sensor", tags=["Sensor Events"])
logger = logging.getLogger("uvicorn.error") or logging.getLogger(__name__)

latest_sensor_serials: Optional[Dict[str, str]] = None
active_sensor_runs: Dict[str, Dict[str, Any]] = {}

# 和 pcba_events.py 類似的結構，但針對 Sensor
SHARED_FILE_PATH = "../shared/sensor_test.txt"

SensorStage = Literal[
    "getSensorIC",
    "sht41",
    "ens210",
    "lps22df",
    "bme690",
    "getHumidity",
    "getTemperature",
    "getPressure",
    "testLeak",
    "testButton",
    "testGreenLED",
    "testOrangeLED",
    "testGreenLEDOff",
    "testOrangeLEDOff",
    "testBuzzer",
    "testSPI",
    "testComplete",
]


class SensorEvent(BaseModel):
    serial: str
    stage: SensorStage
    status: Literal["pending", "testing", "pass", "fail"]
    progress: Optional[int] = Field(default=None, ge=0, le=100)
    detail: Optional[Dict[str, Any]] = None
    timestamp: Optional[datetime] = None


class StartTestRequest(BaseModel):
    serial: str


class SerialFoundRequest(BaseModel):
    serial_wle: str
    serial_wba: Optional[str] = None


class RunStageRequest(BaseModel):
    serial: str
    stage: SensorStage


@router.post("/run-stage")
async def run_sensor_stage(request: RunStageRequest):
    """
    只執行單一測試階段，用於逐項驗證。
    """
    serial = (request.serial or "").strip()
    if not serial:
        raise HTTPException(status_code=400, detail="serial is required")

    logger.info(f"[Sensor:/run-stage] {request.stage} for serial: {serial}")

    try:
        with open(SHARED_FILE_PATH, "w") as f:
            f.write(f"STAGE {request.stage} {serial}\n{datetime.now().isoformat()}\n")

        return {"status": "triggered", "serial": serial, "stage": request.stage}

    except Exception as e:
        logger.exception(f"[Sensor:/run-stage] Failed to write stage command: {e}")
        raise HTTPException(status_code=500, detail="Failed to trigger stage")


@router.post("/read-serial")
async def read_sensor_serial():
    """
    請 sensor_watcher 從裝置讀取序號：寫入 SEARCH 指令到共享檔案。
    結果由 watcher POST 回 /serial-found，再廣播給前端。
    """
    logger.info("[Sensor:/read-serial] Read serial request received")

    try:
        global latest_sensor_serials
        latest_sensor_serials = None
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

    global latest_sensor_serials
    latest_sensor_serials = {"serial_wle": serial_wle, "serial_wba": serial_wba}

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


@router.get("/serial-found/latest")
async def latest_sensor_serial():
    return latest_sensor_serials or {
        "serial_wle": "",
        "serial_wba": "",
    }


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
async def receive_sensor_event(event: SensorEvent, db: Session = Depends(get_db)):
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
        now = event.timestamp or datetime.now()
        if now.tzinfo is not None:
            now = now.replace(tzinfo=None)

        # getSensorIC/testing 是每次 full 或 single 執行的明確起點。
        if stage == "getSensorIC" and status == "testing":
            active_sensor_runs[serial] = {
                "started_at": now,
                "items": {},
                "completion": None,
            }

        run = active_sensor_runs.setdefault(serial, {
            "started_at": now,
            "items": {},
            "completion": None,
        })
        if stage == "testComplete":
            run["completion"] = event.detail or {}
        elif status in ("pass", "fail"):
            run["items"][stage] = {
                "status": status,
                "detail": event.detail or {},
                "tested_at": now,
            }

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

        saved = _try_finalize_sensor_run(serial, db)
        if saved:
            await manager.broadcast({
                "type": "sensor_test_saved",
                "data": {
                    "serial": serial,
                    "run_id": saved.id,
                    "test_result": saved.test_result,
                },
                "timestamp": datetime.now().isoformat(),
            })

        return {"status": "saved" if saved else "accepted", "run_id": saved.id if saved else None}

    except Exception as e:
        logger.exception(f"[Sensor:/events] Failed to process event: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Failed to process event")


def _try_finalize_sensor_run(serial: str, db: Session) -> Optional[SensorTestRun]:
    run = active_sensor_runs.get(serial)
    if not run or not run.get("completion"):
        return None

    completion = run["completion"]
    expected = completion.get("expected_stages") or []
    if any(run["items"].get(stage, {}).get("status") not in ("pass", "fail") for stage in expected):
        return None

    final_result = "PASS" if expected and all(
        run["items"][stage]["status"] == "pass" for stage in expected
    ) else "FAIL"
    db_run = SensorTestRun(
        serial_wle=serial,
        serial_wba=completion.get("serial_wba") or None,
        run_mode=completion.get("run_mode", "full"),
        requested_stage=completion.get("requested_stage") or None,
        test_result=final_result,
        started_at=run["started_at"],
        completed_at=datetime.now(),
    )
    for sequence, stage in enumerate(expected, start=1):
        item = run["items"][stage]
        detail = item["detail"]
        db_run.items.append(SensorTestItem(
            sequence=sequence,
            stage=stage,
            sensor_name=detail.get("sensor"),
            status=item["status"],
            temperature_c=detail.get("temperature"),
            humidity_percent=detail.get("humidity"),
            pressure_hpa=detail.get("pressure"),
            gas_resistance_ohm=detail.get("gas_resistance"),
            detail_json=json.dumps(detail, ensure_ascii=False),
            tested_at=item["tested_at"],
        ))
    db.add(db_run)
    db.commit()
    db.refresh(db_run)
    del active_sensor_runs[serial]
    return db_run


@router.get("/test-runs", response_model=List[SensorTestRunResponse])
def get_sensor_test_runs(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    serial_wle: Optional[str] = None,
    test_result: Optional[str] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    db: Session = Depends(get_db),
):
    query = db.query(SensorTestRun).options(selectinload(SensorTestRun.items))
    if serial_wle:
        query = query.filter(SensorTestRun.serial_wle == serial_wle)
    if test_result:
        query = query.filter(SensorTestRun.test_result == test_result)
    if start_date:
        query = query.filter(SensorTestRun.completed_at >= start_date)
    if end_date:
        query = query.filter(SensorTestRun.completed_at <= end_date)
    return query.order_by(SensorTestRun.completed_at.desc()).offset(skip).limit(limit).all()


@router.delete("/test-runs/{run_id}", status_code=204)
def delete_sensor_test_run(run_id: int, db: Session = Depends(get_db)):
    run = db.query(SensorTestRun).filter(SensorTestRun.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Sensor test run not found")
    db.delete(run)
    db.commit()
    return None
