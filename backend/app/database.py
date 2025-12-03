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
    # Ensure missing columns exist (simple migration)
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
