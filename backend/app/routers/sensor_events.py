from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, selectinload
from sqlalchemy import case, func
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
active_sensor_run_ids: Dict[str, int] = {}
pending_read_started_at: Optional[datetime] = None

SENSOR_RESULT_STAGES = [
    "getSensorIC", "sht41", "ens210", "lps22df", "bme690",
    "testButton", "testGreenLED", "testOrangeLED", "testBuzzer", "testSPI",
]

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
        global latest_sensor_serials, pending_read_started_at
        latest_sensor_serials = None
        pending_read_started_at = datetime.now()
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
async def sensor_serial_found(request: SerialFoundRequest, db: Session = Depends(get_db)):
    """
    sensor_watcher 回報從裝置讀到的 WLE / WBA 序號，廣播給前端自動填入。
    """
    serial_wle = (request.serial_wle or "").strip()
    serial_wba = (request.serial_wba or "").strip()

    if not serial_wle:
        raise HTTPException(status_code=400, detail="serial_wle is required")

    global latest_sensor_serials, pending_read_started_at
    started_at = pending_read_started_at or datetime.now()
    pending_read_started_at = None

    # 每次「讀取序號」都是一個新的測試 session。後續 full/single
    # 測項都更新這一筆，直到下一次讀取序號。
    db_run = SensorTestRun(
        serial_wle=serial_wle,
        serial_wba=serial_wba or None,
        run_mode="session",
        requested_stage=None,
        test_result="PENDING",
        started_at=started_at,
        completed_at=started_at,
    )
    db.add(db_run)
    db.commit()
    db.refresh(db_run)
    active_sensor_run_ids[serial_wle] = db_run.id
    latest_sensor_serials = {
        "serial_wle": serial_wle,
        "serial_wba": serial_wba,
        "run_id": db_run.id,
    }

    logger.info(
        f"[Sensor:/serial-found] Received serials: WLE={serial_wle} WBA={serial_wba}"
    )

    try:
        await manager.broadcast({
            "type": "sensor_serial_found",
            "data": {"serial_wle": serial_wle, "serial_wba": serial_wba, "run_id": db_run.id},
            "timestamp": datetime.now().isoformat(),
        })

        return {"status": "accepted", "serial_wle": serial_wle,
                "serial_wba": serial_wba, "run_id": db_run.id}

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

        saved_run = None
        if stage in SENSOR_RESULT_STAGES and status in ("pass", "fail"):
            saved_run = _save_sensor_session_item(serial, stage, status,
                                                  event.detail or {}, now, db)
        elif stage == "testComplete":
            saved_run = _finalize_sensor_session(serial, event.detail or {}, now, db)

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

        if saved_run:
            await manager.broadcast({
                "type": "sensor_test_updated",
                "data": {
                    "serial": serial,
                    "run_id": saved_run.id,
                    "test_result": saved_run.test_result,
                },
                "timestamp": datetime.now().isoformat(),
            })

        return {"status": "saved" if saved_run else "accepted",
                "run_id": saved_run.id if saved_run else None}

    except Exception as e:
        logger.exception(f"[Sensor:/events] Failed to process event: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Failed to process event")


def _finalize_sensor_session(serial: str, detail: Dict[str, Any], completed_at: datetime,
                             db: Session) -> Optional[SensorTestRun]:
    run_id = active_sensor_run_ids.get(serial)
    db_run = db.query(SensorTestRun).options(selectinload(SensorTestRun.items)).filter(
        SensorTestRun.id == run_id
    ).first() if run_id else None
    if not db_run:
        db_run = db.query(SensorTestRun).options(selectinload(SensorTestRun.items)).filter(
            SensorTestRun.serial_wle == serial,
            SensorTestRun.run_mode == "session",
        ).order_by(SensorTestRun.started_at.desc()).first()
    if not db_run:
        return None

    expected_stages = detail.get("expected_stages")
    statuses = {existing.stage: existing.status for existing in db_run.items}

    if any(value == "fail" for value in statuses.values()):
        db_run.test_result = "FAIL"
    elif expected_stages and all(statuses.get(s) == "pass" for s in expected_stages):
        db_run.test_result = "PASS"
    else:
        if statuses.get("getSensorIC") == "pass" and all(status == "pass" for status in statuses.values()):
            db_run.test_result = "PASS"
        else:
            db_run.test_result = "PENDING"

    db_run.completed_at = completed_at
    db.commit()
    db.refresh(db_run)
    return db_run


def _save_sensor_session_item(serial: str, stage: str, status: str,
                              detail: Dict[str, Any], tested_at: datetime,
                              db: Session) -> Optional[SensorTestRun]:
    run_id = active_sensor_run_ids.get(serial)
    db_run = db.query(SensorTestRun).options(selectinload(SensorTestRun.items)).filter(
        SensorTestRun.id == run_id
    ).first() if run_id else None
    if not db_run:
        # Backend 重啟後恢復該 WLE 最新的 session。
        db_run = db.query(SensorTestRun).options(selectinload(SensorTestRun.items)).filter(
            SensorTestRun.serial_wle == serial,
            SensorTestRun.run_mode == "session",
        ).order_by(SensorTestRun.started_at.desc()).first()
    if not db_run:
        logger.warning("No sensor session for event serial=%s stage=%s", serial, stage)
        return None

    item = next((existing for existing in db_run.items if existing.stage == stage), None)
    if not item:
        item = SensorTestItem(run_id=db_run.id, stage=stage,
                              sequence=SENSOR_RESULT_STAGES.index(stage) + 1)
        db_run.items.append(item)
    item.sensor_name = detail.get("sensor")
    item.status = status
    item.temperature_c = detail.get("temperature")
    item.humidity_percent = detail.get("humidity")
    item.pressure_hpa = detail.get("pressure")
    item.gas_resistance_ohm = detail.get("gas_resistance")
    item.detail_json = json.dumps(detail, ensure_ascii=False)
    item.tested_at = tested_at
    db_run.completed_at = datetime.now()

    statuses = {existing.stage: existing.status for existing in db_run.items}
    if any(value == "fail" for value in statuses.values()):
        db_run.test_result = "FAIL"
    elif statuses and all(value == "pass" for value in statuses.values()):
        db_run.test_result = "PASS"
    else:
        # 依據 getSensorIC 實際探測結果動態判定所需項目
        get_ic_item = next((existing for existing in db_run.items if existing.stage == "getSensorIC"), None)
        if get_ic_item and get_ic_item.detail_json:
            try:
                ic_detail = json.loads(get_ic_item.detail_json)
                required = ["getSensorIC", "testButton", "testGreenLED", "testOrangeLED", "testBuzzer", "testSPI"]
                for sensor_name in ["sht41", "ens210", "lps22df", "bme690"]:
                    if ic_detail.get(sensor_name) is True:
                        required.append(sensor_name)
                if all(statuses.get(name) == "pass" for name in required):
                    db_run.test_result = "PASS"
                else:
                    db_run.test_result = "PENDING"
            except Exception:
                db_run.test_result = "PENDING"
        else:
            db_run.test_result = "PENDING"
    db.commit()
    db.refresh(db_run)
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
        query = query.filter(SensorTestRun.started_at >= start_date)
    if end_date:
        query = query.filter(SensorTestRun.started_at <= end_date)
    return query.order_by(SensorTestRun.started_at.desc()).offset(skip).limit(limit).all()


@router.get("/test-runs/stats")
def get_sensor_test_run_stats(db: Session = Depends(get_db)):
    """Dashboard statistics based on read-serial Sensor sessions."""
    today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    totals = db.query(
        func.count(SensorTestRun.id).label("total"),
        func.sum(case((SensorTestRun.test_result == "PASS", 1), else_=0)).label("passed"),
        func.sum(case((SensorTestRun.test_result == "FAIL", 1), else_=0)).label("failed"),
        func.sum(case((SensorTestRun.test_result == "PENDING", 1), else_=0)).label("pending"),
        func.sum(case((SensorTestRun.started_at >= today_start, 1), else_=0)).label("today_total"),
    ).filter(SensorTestRun.run_mode == "session").one()

    passed = int(totals.passed or 0)
    failed = int(totals.failed or 0)
    pending = int(totals.pending or 0)
    completed = passed + failed
    return {
        "total": int(totals.total or 0),
        "passed": passed,
        "failed": failed,
        "pending": pending,
        "today_total": int(totals.today_total or 0),
        "pass_rate": round((passed / completed) * 100, 1) if completed else 0,
    }


@router.delete("/test-runs/{run_id}", status_code=204)
def delete_sensor_test_run(run_id: int, db: Session = Depends(get_db)):
    run = db.query(SensorTestRun).filter(SensorTestRun.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Sensor test run not found")
    db.delete(run)
    db.commit()
    return None
