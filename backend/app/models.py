from sqlalchemy import Column, Integer, String, Float, DateTime, Text, Boolean
from sqlalchemy.sql import func
from app.database import Base


class TestRecord(Base):
    """測試記錄資料表"""
    __tablename__ = "test_records"

    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(String(100), index=True, nullable=False, comment="設備ID")
    product_name = Column(String(200), nullable=False, comment="產品名稱")
    serial_number = Column(String(100), unique=True, index=True, nullable=False, comment="序號")
    test_station = Column(String(100), nullable=False, comment="測試站別")
    test_result = Column(String(20), nullable=False, comment="測試結果: PASS/FAIL")
    test_time = Column(DateTime, nullable=False, comment="測試時間")
    
    # 測試數據
    test_data = Column(Text, comment="測試數據 (JSON格式)")
    
    # 測試參數
    voltage = Column(Float, comment="電壓")
    current = Column(Float, comment="電流")
    temperature = Column(Float, comment="溫度")
    # 欄位尚未在資料庫建立，暫時移除以避免查詢錯誤
    # uuid = Column(String(100), comment="設備UUID")
    
    # 系統欄位
    uploaded_to_cloud = Column(Boolean, default=False, comment="是否已上傳雲端")
    created_at = Column(DateTime, server_default=func.now(), comment="建立時間")
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), comment="更新時間")
    
    def __repr__(self):
        return f"<TestRecord {self.serial_number} - {self.test_result}>"


class CloudUploadLog(Base):
    """雲端上傳日誌"""
    __tablename__ = "cloud_upload_logs"

    id = Column(Integer, primary_key=True, index=True)
    upload_time = Column(DateTime, server_default=func.now(), comment="上傳時間")
    records_count = Column(Integer, comment="上傳記錄數")
    status = Column(String(20), comment="狀態: SUCCESS/FAILED")
    error_message = Column(Text, comment="錯誤訊息")
    
    def __repr__(self):
        return f"<CloudUploadLog {self.upload_time} - {self.status}>"
