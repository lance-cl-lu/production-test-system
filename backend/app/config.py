from pydantic_settings import BaseSettings
from typing import List


class Settings(BaseSettings):
    # Database
    DATABASE_URL: str = "mysql+pymysql://testuser:testpassword@localhost:3306/production_test"
    
    # Cloud Upload
    CLOUD_UPLOAD_ENABLED: bool = False
    CLOUD_API_URL: str = ""
    CLOUD_API_KEY: str = ""
    
    # Scheduler
    UPLOAD_SCHEDULE_HOURS: int = 1
    
    # CORS
    CORS_ORIGINS: List[str] = ["http://localhost:3000", "http://localhost:3001"]
    
    class Config:
        env_file = ".env"


settings = Settings()
