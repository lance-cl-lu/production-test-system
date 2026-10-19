import re
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import FirmwareFlashCount


router = APIRouter(prefix="/api/firmware-flashes", tags=["Firmware Flashes"])
SERIAL_NUMBER_PATTERN = re.compile(r"^\d{8}$")


def _validate_serial_number(serial_number: str):
    if not SERIAL_NUMBER_PATTERN.fullmatch(serial_number):
        raise HTTPException(status_code=422, detail="serial_number must contain exactly 8 digits")


def _serialize_counts(serial_number: str, record: FirmwareFlashCount | None):
    return {
        "serial_number": serial_number,
        "test_firmware_count": record.test_firmware_count if record else 0,
        "diagnostics_firmware_count": record.diagnostics_firmware_count if record else 0,
    }


@router.get("/{serial_number}")
def get_firmware_flash_counts(serial_number: str, db: Session = Depends(get_db)):
    _validate_serial_number(serial_number)
    record = db.query(FirmwareFlashCount).filter(
        FirmwareFlashCount.serial_number == serial_number
    ).first()
    return _serialize_counts(serial_number, record)


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
