from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool
from contextlib import contextmanager
import logging
from config import Config
from .models import Base

logger = logging.getLogger(__name__)

class DatabaseManager:
    def __init__(self):
        self.engine = None
        self.SessionLocal = None
        self.init_database()
    
    def init_database(self):
        """Initialize database connection and create tables"""
        try:
            # Create engine
            if Config.DATABASE_URL.startswith('sqlite'):
                self.engine = create_engine(
                    Config.DATABASE_URL,
                    connect_args={
                        "check_same_thread": False,
                        "timeout": 20
                    },
                    poolclass=StaticPool,
                    echo=Config.DEBUG
                )
            else:
                self.engine = create_engine(
                    Config.DATABASE_URL,
                    pool_pre_ping=True,
                    echo=Config.DEBUG
                )
            
            # Create session factory
            self.SessionLocal = sessionmaker(
                autocommit=False,
                autoflush=False,
                bind=self.engine
            )
            
            # Create tables
            Base.metadata.create_all(bind=self.engine)
            logger.info("Database initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize database: {e}")
            raise
    
    @contextmanager
    def get_session(self):
        """Get database session with automatic cleanup"""
        session = self.SessionLocal()
        try:
            yield session
            session.commit()
        except Exception as e:
            session.rollback()
            logger.error(f"Database session error: {e}")
            raise
        finally:
            session.close()
    
    def get_session_sync(self) -> Session:
        """Get synchronous database session"""
        return self.SessionLocal()
    
    def close(self):
        """Close database connections"""
        if self.engine:
            self.engine.dispose()

# Global database manager instance
db_manager = DatabaseManager()

def get_db_session():
    """Dependency for getting database session"""
    return db_manager.get_session_sync()

def init_db():
    """Initialize database (for external use)"""
    return db_manager.init_database()

