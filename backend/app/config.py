from pydantic_settings import BaseSettings
from typing import List


class Settings(BaseSettings):
    # Database
    DATABASE_URL: str = "mysql+pymysql://testuser:testpassword@localhost:3306/production_test"
    
    # Cloud Upload
    CLOUD_UPLOAD_ENABLED: bool = False
    CLOUD_API_URL: str = ""
    CLOUD_API_KEY: str = ""
    CLOUD_SYNC_BATCH_SIZE: int = 100
    CLOUD_SYNC_INTERVAL_SECONDS: int = 10
    
    # Scheduler
    UPLOAD_SCHEDULE_HOURS: int = 1
    
    # CORS
    CORS_ORIGINS: List[str] = [
        "http://localhost:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:3001",
        "http://[::1]:3000",
        "http://[::1]:3001",
        "null",
    ]
    CORS_ORIGIN_REGEX: str = r"^https?://(localhost|127\.0\.0\.1|\[::1\]):\d+$"
    
    class Config:
        env_file = ".env"


settings = Settings()
