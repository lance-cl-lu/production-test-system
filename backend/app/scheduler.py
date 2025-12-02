import httpx
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from datetime import datetime
from app.config import settings
from app.database import SessionLocal
from app.services import TestRecordService, CloudUploadService
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()


async def upload_to_cloud():
    """定時上傳資料到雲端"""
    if not settings.CLOUD_UPLOAD_ENABLED:
        logger.info("Cloud upload is disabled")
        return
    
    logger.info("Starting cloud upload task...")
    db = SessionLocal()
    
    try:
        # 取得未上傳的記錄
        unuploaded_records = TestRecordService.get_unuploaded_records(db)
        
        if not unuploaded_records:
            logger.info("No records to upload")
            return
        
        # 準備上傳資料
        records_data = [
            {
                "id": record.id,
                "device_id": record.device_id,
                "product_name": record.product_name,
                "serial_number": record.serial_number,
                "test_station": record.test_station,
                "test_result": record.test_result,
                "test_time": record.test_time.isoformat(),
                "test_data": record.test_data,
                "voltage": record.voltage,
                "current": record.current,
                "temperature": record.temperature,
            }
            for record in unuploaded_records
        ]
        
        # 發送到雲端 API
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                settings.CLOUD_API_URL,
                json={"records": records_data},
                headers={"Authorization": f"Bearer {settings.CLOUD_API_KEY}"}
            )
            
            if response.status_code == 200:
                # 標記為已上傳
                record_ids = [r.id for r in unuploaded_records]
                TestRecordService.mark_as_uploaded(db, record_ids)
                
                # 記錄成功日誌
                CloudUploadService.create_upload_log(
                    db,
                    records_count=len(unuploaded_records),
                    status="SUCCESS"
                )
                logger.info(f"Successfully uploaded {len(unuploaded_records)} records")
            else:
                # 記錄失敗日誌
                error_msg = f"HTTP {response.status_code}: {response.text}"
                CloudUploadService.create_upload_log(
                    db,
                    records_count=len(unuploaded_records),
                    status="FAILED",
                    error_message=error_msg
                )
                logger.error(f"Upload failed: {error_msg}")
    
    except Exception as e:
        logger.error(f"Upload error: {str(e)}")
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
        # 每小時執行一次
        scheduler.add_job(
            upload_to_cloud,
            'interval',
            hours=settings.UPLOAD_SCHEDULE_HOURS,
            id='cloud_upload',
            replace_existing=True
        )
        scheduler.start()
        logger.info(f"Scheduler started: upload every {settings.UPLOAD_SCHEDULE_HOURS} hour(s)")
    else:
        logger.info("Scheduler not started: cloud upload is disabled")


def stop_scheduler():
    """停止排程器"""
    scheduler.shutdown()
    logger.info("Scheduler stopped")
