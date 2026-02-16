"""
Database session management
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.logging_config import get_logger

logger = get_logger(__name__)

# Use the database_url property from settings
# PostgreSQL connection configuration
connection_string = settings.database_url

# Log connection info (without password)
logger.info(f"Database connection: {settings.DB_HOST}:{settings.DB_PORT}/{settings.DB_NAME} (PostgreSQL)")

# Create engine
# Set session timezone to UTC so TIMESTAMP WITHOUT TIME ZONE columns behave
# consistently regardless of the server's or OS's local timezone setting.
engine = create_engine(
    connection_string,
    echo=False,  # Set to True for SQL query logging
    pool_pre_ping=True,  # Verify connections before using
    pool_recycle=3600,  # Recycle connections after 1 hour
    connect_args={"options": "-c timezone=utc"},
)

# Create session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    """
    Dependency for getting database session

    Usage in FastAPI endpoints:
        @router.get("/items")
        def get_items(db: Session = Depends(get_db)):
            items = db.query(Item).all()
            return items
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
