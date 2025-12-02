from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime
from app.database import get_db
from app.schemas import TestRecordCreate, TestRecordResponse, TestRecordUpdate
from app.services import TestRecordService

router = APIRouter(prefix="/api/test-records", tags=["Test Records"])


@router.post("/", response_model=TestRecordResponse, status_code=201)
def create_test_record(
    record: TestRecordCreate,
    db: Session = Depends(get_db)
):
    """建立測試記錄"""
    try:
        return TestRecordService.create_test_record(db, record)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/", response_model=List[TestRecordResponse])
def get_test_records(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    device_id: Optional[str] = None,
    test_result: Optional[str] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    db: Session = Depends(get_db)
):
    """取得測試記錄列表"""
    return TestRecordService.get_test_records(
        db, skip, limit, device_id, test_result, start_date, end_date
    )


@router.get("/{record_id}", response_model=TestRecordResponse)
def get_test_record(record_id: int, db: Session = Depends(get_db)):
    """取得單筆測試記錄"""
    record = TestRecordService.get_test_record(db, record_id)
    if not record:
        raise HTTPException(status_code=404, detail="Record not found")
    return record


@router.put("/{record_id}", response_model=TestRecordResponse)
def update_test_record(
    record_id: int,
    record_update: TestRecordUpdate,
    db: Session = Depends(get_db)
):
    """更新測試記錄"""
    record = TestRecordService.update_test_record(db, record_id, record_update)
    if not record:
        raise HTTPException(status_code=404, detail="Record not found")
    return record


@router.delete("/{record_id}", status_code=204)
def delete_test_record(record_id: int, db: Session = Depends(get_db)):
    """刪除測試記錄"""
    if not TestRecordService.delete_test_record(db, record_id):
        raise HTTPException(status_code=404, detail="Record not found")
    return None
