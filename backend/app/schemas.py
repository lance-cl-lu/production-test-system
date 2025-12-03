from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, Dict, Any


class TestRecordBase(BaseModel):
    device_id: str = Field(..., description="設備ID")
    product_name: str = Field(..., description="產品名稱")
    serial_number: str = Field(..., description="序號")
    test_station: str = Field(..., description="測試站別")
    test_result: str = Field(..., description="測試結果: PASS/FAIL")
    test_time: datetime = Field(..., description="測試時間")
    test_data: Optional[str] = Field(None, description="測試數據 (JSON格式)")
    voltage: Optional[float] = Field(None, description="電壓")
    current: Optional[float] = Field(None, description="電流")
    temperature: Optional[float] = Field(None, description="溫度")
    humidity: Optional[float] = Field(None, description="濕度")
    pressure: Optional[float] = Field(None, description="壓力")
    uuid: Optional[str] = Field(None, description="設備UUID")


class TestRecordCreate(TestRecordBase):
    pass


class TestRecordResponse(TestRecordBase):
    id: int
    uploaded_to_cloud: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class TestRecordUpdate(BaseModel):
    device_id: Optional[str] = None
    product_name: Optional[str] = None
    test_result: Optional[str] = None
    test_data: Optional[str] = None
    voltage: Optional[float] = None
    current: Optional[float] = None
    temperature: Optional[float] = None
    humidity: Optional[float] = None
    pressure: Optional[float] = None
    uuid: Optional[str] = None


class CloudUploadLogResponse(BaseModel):
    id: int
    upload_time: datetime
    records_count: int
    status: str
    error_message: Optional[str]

    class Config:
        from_attributes = True


class WebSocketMessage(BaseModel):
    type: str  # "test_result", "system_status", etc.
    data: Dict[str, Any]
    timestamp: datetime = Field(default_factory=datetime.now)
