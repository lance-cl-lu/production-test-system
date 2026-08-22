import os
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String, Text, case, create_engine, func
from sqlalchemy.orm import Session, declarative_base, relationship, selectinload, sessionmaker


DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "mysql+pymysql://clouduser:cloudpassword@cloud-mysql:3306/production_test_cloud",
)
CLOUD_API_KEY = os.getenv("CLOUD_API_KEY", "local-cloud-key")

engine = create_engine(DATABASE_URL, pool_pre_ping=True, pool_recycle=3600)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
Base = declarative_base()


class CloudSensorRun(Base):
    __tablename__ = "cloud_sensor_test_runs"
    id = Column(Integer, primary_key=True)
    sync_uuid = Column(String(36), unique=True, nullable=False, index=True)
    serial_wle = Column(String(100), nullable=False, index=True)
    serial_wba = Column(String(100), index=True)
    run_mode = Column(String(20), nullable=False)
    requested_stage = Column(String(64))
    test_result = Column(String(20), nullable=False, index=True)
    started_at = Column(DateTime, nullable=False, index=True)
    completed_at = Column(DateTime, nullable=False)
    synced_at = Column(DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)
    items = relationship("CloudSensorItem", cascade="all, delete-orphan", order_by="CloudSensorItem.sequence")


class CloudSensorItem(Base):
    __tablename__ = "cloud_sensor_test_items"
    id = Column(Integer, primary_key=True)
    sync_uuid = Column(String(36), unique=True, nullable=False, index=True)
    run_id = Column(Integer, ForeignKey("cloud_sensor_test_runs.id", ondelete="CASCADE"), nullable=False)
    sequence = Column(Integer, nullable=False)
    stage = Column(String(64), nullable=False)
    sensor_name = Column(String(32))
    status = Column(String(20), nullable=False)
    temperature_c = Column(Float)
    humidity_percent = Column(Float)
    pressure_hpa = Column(Float)
    gas_resistance_ohm = Column(Float)
    detail_json = Column(Text)
    tested_at = Column(DateTime, nullable=False)


class SyncEvent(BaseModel):
    outbox_id: int
    entity_type: str
    entity_uuid: str
    operation: str
    payload: Dict[str, Any]


class SyncBatch(BaseModel):
    events: List[SyncEvent]


app = FastAPI(title="Production Test Cloud Receiver", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3100", "http://127.0.0.1:3100"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup():
    Base.metadata.create_all(engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def parse_datetime(value: Optional[str]) -> datetime:
    return datetime.fromisoformat(value) if value else datetime.now()


def serialize_run(run: CloudSensorRun) -> Dict[str, Any]:
    return {
        "sync_uuid": run.sync_uuid,
        "serial_wle": run.serial_wle,
        "serial_wba": run.serial_wba,
        "run_mode": run.run_mode,
        "requested_stage": run.requested_stage,
        "test_result": run.test_result,
        "started_at": run.started_at.isoformat(),
        "completed_at": run.completed_at.isoformat(),
        "synced_at": run.synced_at.isoformat(),
        "items": [{
            "sync_uuid": item.sync_uuid,
            "sequence": item.sequence,
            "stage": item.stage,
            "sensor_name": item.sensor_name,
            "status": item.status,
            "temperature_c": item.temperature_c,
            "humidity_percent": item.humidity_percent,
            "pressure_hpa": item.pressure_hpa,
            "gas_resistance_ohm": item.gas_resistance_ohm,
            "detail_json": item.detail_json,
            "tested_at": item.tested_at.isoformat(),
        } for item in run.items],
    }


@app.get("/health")
def health():
    return {"status": "healthy"}


@app.post("/api/v1/sync/batch")
def sync_batch(batch: SyncBatch, x_api_key: str = Header(default=""), db: Session = Depends(get_db)):
    if x_api_key != CLOUD_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")

    accepted = 0
    for event in batch.events:
        if event.entity_type != "sensor_test_run" or event.operation != "upsert":
            continue
        payload = event.payload
        run = db.query(CloudSensorRun).filter(CloudSensorRun.sync_uuid == event.entity_uuid).first()
        if not run:
            run = CloudSensorRun(sync_uuid=event.entity_uuid)
            db.add(run)
        for field in ("serial_wle", "serial_wba", "run_mode", "requested_stage", "test_result"):
            setattr(run, field, payload.get(field))
        run.started_at = parse_datetime(payload.get("started_at"))
        run.completed_at = parse_datetime(payload.get("completed_at"))
        run.synced_at = datetime.now()
        db.flush()

        for item_payload in payload.get("items", []):
            item = db.query(CloudSensorItem).filter(
                CloudSensorItem.sync_uuid == item_payload["sync_uuid"]
            ).first()
            if not item:
                item = CloudSensorItem(sync_uuid=item_payload["sync_uuid"], run_id=run.id)
                db.add(item)
            for field in ("sequence", "stage", "sensor_name", "status", "temperature_c",
                          "humidity_percent", "pressure_hpa", "gas_resistance_ohm", "detail_json"):
                setattr(item, field, item_payload.get(field))
            item.tested_at = parse_datetime(item_payload.get("tested_at"))
        accepted += 1

    db.commit()
    return {"status": "accepted", "accepted": accepted}


@app.get("/api/v1/dashboard/stats")
def stats(db: Session = Depends(get_db)):
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    row = db.query(
        func.count(CloudSensorRun.id).label("total"),
        func.sum(case((CloudSensorRun.test_result == "PASS", 1), else_=0)).label("passed"),
        func.sum(case((CloudSensorRun.test_result == "FAIL", 1), else_=0)).label("failed"),
        func.sum(case((CloudSensorRun.test_result == "PENDING", 1), else_=0)).label("pending"),
        func.sum(case((CloudSensorRun.started_at >= today, 1), else_=0)).label("today_total"),
    ).one()
    passed, failed = int(row.passed or 0), int(row.failed or 0)
    completed = passed + failed
    return {"total": int(row.total or 0), "passed": passed, "failed": failed,
            "pending": int(row.pending or 0), "today_total": int(row.today_total or 0),
            "pass_rate": round(passed / completed * 100, 1) if completed else 0}


@app.get("/api/v1/sensor-runs")
def sensor_runs(skip: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=500),
                db: Session = Depends(get_db)):
    runs = db.query(CloudSensorRun).options(selectinload(CloudSensorRun.items)).order_by(
        CloudSensorRun.started_at.desc()
    ).offset(skip).limit(limit).all()
    return [serialize_run(run) for run in runs]
