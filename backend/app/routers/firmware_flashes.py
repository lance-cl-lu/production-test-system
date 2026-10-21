import re
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import FirmwareFlashCount, FirmwareFlashRecord, FirmwareFlashSummary


router = APIRouter(prefix="/api/firmware-flashes", tags=["Firmware Flashes"])
SERIAL_NUMBER_PATTERN = re.compile(r"^\d{8}$")


class FirmwareFlashRecordRequest(BaseModel):
    serial_wle: str = Field(min_length=1, max_length=100)
    serial_wba: str = Field(min_length=1, max_length=100)
    firmware_type: Literal["test", "diagnostics"]
    diagnostics_number: Optional[str] = None


def _validate_serial_number(serial_number: str):
    if not SERIAL_NUMBER_PATTERN.fullmatch(serial_number):
        raise HTTPException(status_code=422, detail="serial_number must contain exactly 8 digits")


def _serialize_counts(serial_number: str, record: FirmwareFlashCount | None):
    return {
        "serial_number": serial_number,
        "test_firmware_count": record.test_firmware_count if record else 0,
        "diagnostics_firmware_count": record.diagnostics_firmware_count if record else 0,
    }


@router.get("/")
def list_firmware_flash_records(db: Session = Depends(get_db)):
    return db.query(FirmwareFlashRecord).order_by(FirmwareFlashRecord.updated_at.desc()).all()


@router.post("/record-success")
def record_pcba_firmware_flash_success(
    request: FirmwareFlashRecordRequest,
    db: Session = Depends(get_db),
):
    if request.firmware_type == "diagnostics" and not SERIAL_NUMBER_PATTERN.fullmatch(
        request.diagnostics_number or ""
    ):
        raise HTTPException(status_code=422, detail="diagnostics_number must contain exactly 8 digits")

    count_column = (
        FirmwareFlashRecord.test_firmware_count
        if request.firmware_type == "test"
        else FirmwareFlashRecord.diagnostics_firmware_count
    )
    record = db.query(FirmwareFlashRecord).filter(
        FirmwareFlashRecord.serial_wle == request.serial_wle,
        FirmwareFlashRecord.serial_wba == request.serial_wba,
    ).first()

    if record is None:
        record = FirmwareFlashRecord(
            serial_wle=request.serial_wle,
            serial_wba=request.serial_wba,
            test_firmware_count=1 if request.firmware_type == "test" else 0,
            diagnostics_firmware_count=1 if request.firmware_type == "diagnostics" else 0,
            diagnostics_number=request.diagnostics_number if request.firmware_type == "diagnostics" else None,
        )
        db.add(record)
        try:
            db.commit()
            db.refresh(record)
            return record
        except IntegrityError:
            # If another request created this PCBA record concurrently, increment it below.
            db.rollback()

    updates = {
        count_column: count_column + 1,
        FirmwareFlashRecord.updated_at: func.now(),
    }
    if request.firmware_type == "diagnostics":
        updates[FirmwareFlashRecord.diagnostics_number] = request.diagnostics_number
    db.query(FirmwareFlashRecord).filter(
        FirmwareFlashRecord.serial_wle == request.serial_wle,
        FirmwareFlashRecord.serial_wba == request.serial_wba,
    ).update(updates, synchronize_session=False)
    db.commit()
    return db.query(FirmwareFlashRecord).filter(
        FirmwareFlashRecord.serial_wle == request.serial_wle,
        FirmwareFlashRecord.serial_wba == request.serial_wba,
    ).first()


@router.post("/test/success")
def record_successful_test_firmware_flash(db: Session = Depends(get_db)):
    summary = db.query(FirmwareFlashSummary).filter(FirmwareFlashSummary.id == 1).first()
    if summary is None:
        summary = FirmwareFlashSummary(id=1, test_firmware_count=1)
        db.add(summary)
        try:
            db.commit()
            db.refresh(summary)
            return {"test_firmware_count": summary.test_firmware_count}
        except IntegrityError:
            # Handle simultaneous first writes from multiple stations.
            db.rollback()

    db.query(FirmwareFlashSummary).filter(FirmwareFlashSummary.id == 1).update(
        {
            FirmwareFlashSummary.test_firmware_count: FirmwareFlashSummary.test_firmware_count + 1,
            FirmwareFlashSummary.updated_at: func.now(),
        },
        synchronize_session=False,
    )
    db.commit()
    summary = db.query(FirmwareFlashSummary).filter(FirmwareFlashSummary.id == 1).first()
    return {"test_firmware_count": summary.test_firmware_count}


@router.get("/{serial_number}")
def get_firmware_flash_counts(serial_number: str, db: Session = Depends(get_db)):
    _validate_serial_number(serial_number)
    legacy_record = db.query(FirmwareFlashCount).filter(
        FirmwareFlashCount.serial_number == serial_number
    ).first()
    pcba_diagnostics_count = db.query(
        func.coalesce(func.sum(FirmwareFlashRecord.diagnostics_firmware_count), 0)
    ).filter(FirmwareFlashRecord.diagnostics_number == serial_number).scalar()
    return {
        "serial_number": serial_number,
        "test_firmware_count": legacy_record.test_firmware_count if legacy_record else 0,
        "diagnostics_firmware_count": (legacy_record.diagnostics_firmware_count if legacy_record else 0)
        + int(pcba_diagnostics_count or 0),
    }


@router.post("/{serial_number}/{firmware_type}/success")
def record_successful_firmware_flash(
    serial_number: str,
    firmware_type: Literal["test", "diagnostics"],
    db: Session = Depends(get_db),
):
    _validate_serial_number(serial_number)
    counter = (
        FirmwareFlashCount.test_firmware_count
        if firmware_type == "test"
        else FirmwareFlashCount.diagnostics_firmware_count
    )

    record = db.query(FirmwareFlashCount).filter(
        FirmwareFlashCount.serial_number == serial_number
    ).first()
    if record is None:
        record = FirmwareFlashCount(
            serial_number=serial_number,
            test_firmware_count=1 if firmware_type == "test" else 0,
            diagnostics_firmware_count=1 if firmware_type == "diagnostics" else 0,
        )
        db.add(record)
        try:
            db.commit()
            db.refresh(record)
            return _serialize_counts(serial_number, record)
        except IntegrityError:
            # Another station may have inserted this number concurrently.
            db.rollback()

    db.query(FirmwareFlashCount).filter(
        FirmwareFlashCount.serial_number == serial_number
    ).update(
        {
            counter: counter + 1,
            FirmwareFlashCount.updated_at: func.now(),
        },
        synchronize_session=False,
    )
    db.commit()
    record = db.query(FirmwareFlashCount).filter(
        FirmwareFlashCount.serial_number == serial_number
    ).first()
    return _serialize_counts(serial_number, record)
