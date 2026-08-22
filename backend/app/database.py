from sqlalchemy import create_engine, inspect, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from app.config import settings

engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    pool_recycle=3600,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    """Database session dependency"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Initialize database tables"""
    Base.metadata.create_all(bind=engine)
    # 舊 test_records 的相容性 migration；Sensor IQC 新表由 metadata 建立。
    try:
        insp = inspect(engine)
        cols = [c['name'] for c in insp.get_columns('test_records')]
        with engine.connect() as conn:
            if 'humidity' not in cols:
                conn.execute(text('ALTER TABLE test_records ADD COLUMN humidity DOUBLE NULL'))
            if 'pressure' not in cols:
                conn.execute(text('ALTER TABLE test_records ADD COLUMN pressure DOUBLE NULL'))
            conn.commit()
    except Exception:
        # Best-effort; skip if any issue
        pass

    # 相容舊版 Sensor session：早期會因未偵測到 sht41 而將已通過的
    # session 留在 PENDING。以實際已儲存的測項終態重新計算。
    try:
        with engine.begin() as conn:
            conn.execute(text("""
                UPDATE sensor_test_runs AS run
                SET test_result = CASE
                    WHEN EXISTS (
                        SELECT 1 FROM sensor_test_items AS item
                        WHERE item.run_id = run.id AND item.status = 'fail'
                    ) THEN 'FAIL'
                    WHEN EXISTS (
                        SELECT 1 FROM sensor_test_items AS item
                        WHERE item.run_id = run.id AND item.status = 'pass'
                    ) THEN 'PASS'
                    ELSE 'PENDING'
                END
                WHERE run.run_mode = 'session'
            """))
    except Exception:
        # Sensor tables 尚未建立或 DB dialect 不支援時，不阻斷啟動。
        pass
