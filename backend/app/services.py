from sqlalchemy.orm import Session
from sqlalchemy import desc, and_
from typing import List, Optional
from datetime import datetime
from app.models import TestRecord, CloudUploadLog
from app.schemas import TestRecordCreate, TestRecordUpdate


class TestRecordService:
    """測試記錄服務"""
    
    @staticmethod
    def create_test_record(db: Session, record: TestRecordCreate) -> TestRecord:
        """建立測試記錄"""
        db_record = TestRecord(**record.model_dump())
        db.add(db_record)
        db.commit()
        db.refresh(db_record)
        return db_record
    
    @staticmethod
    def get_test_record(db: Session, record_id: int) -> Optional[TestRecord]:
        """取得單筆測試記錄"""
        return db.query(TestRecord).filter(TestRecord.id == record_id).first()
    
    @staticmethod
    def get_test_records(
        db: Session,
        skip: int = 0,
        limit: int = 100,
        device_id: Optional[str] = None,
        test_result: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> List[TestRecord]:
        """取得測試記錄列表（支援篩選）"""
        query = db.query(TestRecord)
        
        if device_id:
            query = query.filter(TestRecord.device_id == device_id)
        if test_result:
            query = query.filter(TestRecord.test_result == test_result)
        if start_date:
            query = query.filter(TestRecord.test_time >= start_date)
        if end_date:
            query = query.filter(TestRecord.test_time <= end_date)
        
        return query.order_by(desc(TestRecord.test_time)).offset(skip).limit(limit).all()
    
    @staticmethod
    def update_test_record(
        db: Session,
        record_id: int,
        record_update: TestRecordUpdate
    ) -> Optional[TestRecord]:
        """更新測試記錄"""
        db_record = db.query(TestRecord).filter(TestRecord.id == record_id).first()
        if db_record:
            update_data = record_update.model_dump(exclude_unset=True)
            for key, value in update_data.items():
                setattr(db_record, key, value)
            db.commit()
            db.refresh(db_record)
        return db_record
    
    @staticmethod
    def delete_test_record(db: Session, record_id: int) -> bool:
        """刪除測試記錄"""
        db_record = db.query(TestRecord).filter(TestRecord.id == record_id).first()
        if db_record:
            db.delete(db_record)
            db.commit()
            return True
        return False
    
    @staticmethod
    def get_unuploaded_records(db: Session) -> List[TestRecord]:
        """取得未上傳至雲端的記錄"""
        return db.query(TestRecord).filter(TestRecord.uploaded_to_cloud == False).all()
    
    @staticmethod
    def mark_as_uploaded(db: Session, record_ids: List[int]):
        """標記記錄為已上傳"""
        db.query(TestRecord).filter(TestRecord.id.in_(record_ids)).update(
            {"uploaded_to_cloud": True},
            synchronize_session=False
        )
        db.commit()


class CloudUploadService:
    """雲端上傳服務"""
    
    @staticmethod
    def create_upload_log(
        db: Session,
        records_count: int,
        status: str,
        error_message: Optional[str] = None
    ) -> CloudUploadLog:
        """建立上傳日誌"""
        log = CloudUploadLog(
            records_count=records_count,
            status=status,
            error_message=error_message
        )
        db.add(log)
        db.commit()
        db.refresh(log)
        return log
    
    @staticmethod
    def get_upload_logs(db: Session, limit: int = 50) -> List[CloudUploadLog]:
        """取得上傳日誌"""
        return db.query(CloudUploadLog).order_by(desc(CloudUploadLog.upload_time)).limit(limit).all()
