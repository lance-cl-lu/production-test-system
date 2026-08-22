import httpx
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from datetime import datetime
from app.config import settings
from app.database import SessionLocal
from app.models import CloudSyncOutbox, SensorTestRun
from app.services import CloudUploadService
import json
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()


def _run_payload(run):
    return {
        "sync_uuid": run.sync_uuid, "serial_wle": run.serial_wle,
        "serial_wba": run.serial_wba, "run_mode": run.run_mode,
        "requested_stage": run.requested_stage, "test_result": run.test_result,
        "started_at": run.started_at.isoformat(), "completed_at": run.completed_at.isoformat(),
        "items": [{
            "sync_uuid": item.sync_uuid, "sequence": item.sequence, "stage": item.stage,
            "sensor_name": item.sensor_name, "status": item.status,
            "temperature_c": item.temperature_c, "humidity_percent": item.humidity_percent,
            "pressure_hpa": item.pressure_hpa, "gas_resistance_ohm": item.gas_resistance_ohm,
            "detail_json": item.detail_json, "tested_at": item.tested_at.isoformat(),
        } for item in run.items],
    }


def seed_historical_sensor_runs(db):
    queued = {row[0] for row in db.query(CloudSyncOutbox.entity_uuid).filter(
        CloudSyncOutbox.entity_type == "sensor_test_run"
    ).all()}
    for run in db.query(SensorTestRun).filter(SensorTestRun.run_mode == "session").all():
        if run.sync_uuid not in queued:
            db.add(CloudSyncOutbox(
                entity_type="sensor_test_run", entity_uuid=run.sync_uuid,
                operation="upsert", payload_json=json.dumps(_run_payload(run), ensure_ascii=False),
            ))
    db.commit()


async def upload_to_cloud():
    """定時上傳資料到雲端"""
    if not settings.CLOUD_UPLOAD_ENABLED:
        logger.info("Cloud upload is disabled")
        return
    
    logger.info("Starting cloud upload task...")
    db = SessionLocal()
    
    try:
        seed_historical_sensor_runs(db)
        pending = db.query(CloudSyncOutbox).filter(
            CloudSyncOutbox.status.in_(["PENDING", "FAILED"])
        ).order_by(CloudSyncOutbox.id).limit(settings.CLOUD_SYNC_BATCH_SIZE).all()
        
        if not pending:
            logger.info("No records to upload")
            return
        
        events = [{
            "outbox_id": entry.id,
            "entity_type": entry.entity_type,
            "entity_uuid": entry.entity_uuid,
            "operation": entry.operation,
            "payload": json.loads(entry.payload_json),
        } for entry in pending]
        
        # 發送到雲端 API
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                settings.CLOUD_API_URL,
                json={"events": events},
                headers={"X-API-Key": settings.CLOUD_API_KEY},
            )
            
            if response.status_code in (200, 201):
                uploaded_at = datetime.now()
                for entry in pending:
                    entry.status = "UPLOADED"
                    entry.uploaded_at = uploaded_at
                    entry.last_error = None
                db.commit()
                
                # 記錄成功日誌
                CloudUploadService.create_upload_log(
                    db,
                    records_count=len(pending),
                    status="SUCCESS"
                )
                logger.info(f"Successfully uploaded {len(pending)} cloud events")
            else:
                # 記錄失敗日誌
                error_msg = f"HTTP {response.status_code}: {response.text}"
                CloudUploadService.create_upload_log(
                    db,
                    records_count=len(pending),
                    status="FAILED",
                    error_message=error_msg
                )
                logger.error(f"Upload failed: {error_msg}")
                for entry in pending:
                    entry.status = "FAILED"
                    entry.retry_count += 1
                    entry.last_error = error_msg[:2000]
                db.commit()
    
    except Exception as e:
        logger.error(f"Upload error: {str(e)}")
        if 'pending' in locals():
            for entry in pending:
                entry.status = "FAILED"
                entry.retry_count += 1
                entry.last_error = str(e)[:2000]
            db.commit()
        CloudUploadService.create_upload_log(
            db,
            records_count=0,
            status="FAILED",
            error_message=str(e)
        )
    finally:
        db.close()


def start_scheduler():
    """啟動排程器"""
    if settings.CLOUD_UPLOAD_ENABLED:
        scheduler.add_job(
            upload_to_cloud,
            'interval',
            seconds=settings.CLOUD_SYNC_INTERVAL_SECONDS,
            id='cloud_upload',
            replace_existing=True
        )
        scheduler.start()
        logger.info("Cloud sync scheduler started: every %s seconds",
                    settings.CLOUD_SYNC_INTERVAL_SECONDS)
    else:
        logger.info("Scheduler not started: cloud upload is disabled")


def stop_scheduler():
    """停止排程器"""
    scheduler.shutdown()
    logger.info("Scheduler stopped")
