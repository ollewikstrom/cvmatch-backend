import os
import time
import uuid
from datetime import datetime
from time import perf_counter
from dotenv import load_dotenv
from sqlalchemy import create_engine, Column, String, Integer, Text, DateTime, ForeignKey
from sqlalchemy.orm import sessionmaker, declarative_base, scoped_session, relationship
from sqlalchemy.exc import OperationalError

# Load environment variables
load_dotenv()

# SQLAlchemy base and session
Base = declarative_base()
engine = None
SessionLocal = None


def init_db():
    """
    Initialize the database connection and create tables based on the environment.
    """
    global engine, SessionLocal

    # Get the environment setting
    environment = os.getenv("ENVIRONMENT", "dev")

    # Configure database URI based on environment
    if environment == "dev":
        database_url = (
            f"mssql+pyodbc://{os.getenv('DB_USERNAME')}:{os.getenv('DB_PASSWORD')}@"
            f"{os.getenv('DB_SERVER')}.database.windows.net:1433/{os.getenv('DB_NAME')}?driver=ODBC+Driver+18+for+SQL+Server&Encrypt=yes&TrustServerCertificate=yes"
        )
    elif environment == "test":
        database_url = "sqlite:///test.db"  # Test environment uses SQLite
    else:
        print("Using Azure SQL")
        database_url = os.getenv("AZURE_SQL_CONN_STRING")

    # Create the SQLAlchemy engine with a connection pool
    engine = create_engine(
        database_url,
        pool_size=10,  # Default pool size for concurrent requests
        max_overflow=5,  # Extra connections allowed beyond pool_size
        pool_timeout=30,  # Time to wait for a connection before timeout
        connect_args={"check_same_thread": False} if "sqlite" in database_url else {},
    )

    # Configure the session factory
    SessionLocal = scoped_session(sessionmaker(autocommit=False, autoflush=False, bind=engine))

    # Create all tables
    Base.metadata.create_all(bind=engine)


# Dependency to inject the database session into FastAPI routes
def db_session():
    """
    Database session dependency for FastAPI routes.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# Models
class ResponseSummary(Base):
    __tablename__ = "response_summaries"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    summary = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    cv_name = Column(String(255), nullable=True)
    job_listing_name = Column(String(255), nullable=True)
    job_listing_url = Column(String(255), nullable=True)

    # Relationship to Skills
    skills = relationship("Skill", back_populates="response_summary", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<ResponseSummary {self.id}>"


class Skill(Base):
    __tablename__ = "skills"

    id = Column(Integer, primary_key=True)
    response_summary_id = Column(String(36), ForeignKey("response_summaries.id"), nullable=False)
    skill_name = Column(String(255), nullable=False)
    reason = Column(Text, nullable=True)
    level_of_importance = Column(String(50), nullable=True)  # e.g., "MUST HAVE", "SHOULD HAVE"
    match_label = Column(String(50), nullable=True)  # e.g., "MATCH", "MISSING", "PARTIAL", "UNSURE"

    # Relationship to ResponseSummary
    response_summary = relationship("ResponseSummary", back_populates="skills")

    def __repr__(self):
        return f"<Skill {self.id}: {self.skill_name}>"


# Retry decorator for database operations
def with_retry(retries=3, delay=5):
    """
    Decorator for retrying database operations in case of transient failures.
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            for attempt in range(retries):
                try:
                    return func(*args, **kwargs)
                except OperationalError as e:
                    if attempt < retries - 1:
                        retry_delay = delay + (0.5 * attempt)  # Incremental backoff
                        print(f"Database operation failed. Retrying in {retry_delay:.2f} seconds... (Attempt {attempt + 1} of {retries})")
                        time.sleep(retry_delay)
                    else:
                        print("All retries exhausted. Raising the exception.")
                        raise e
        return wrapper
    return decorator


@with_retry(retries=3, delay=5)
def save_openai_response(response_data, cv_name, job_listing_name, job_listing_url):
    """
    Save OpenAI response and associated skills to the database.
    """
    session = SessionLocal()
    try:
        total_start_time = perf_counter()

        # Step 1: Save the summary
        step_start_time = perf_counter()
        summary_text = response_data.get("summary", "")
        response_summary = ResponseSummary(
            summary=summary_text,
            cv_name=cv_name,
            job_listing_name=job_listing_name,
            job_listing_url=job_listing_url,
        )
        session.add(response_summary)
        session.commit()
        step_end_time = perf_counter()
        print(f"Step 1 (Save Summary): {step_end_time - step_start_time:.4f} seconds")

        # Step 2: Save the skills
        step_start_time = perf_counter()
        for skill_data in response_data.get("skills", []):
            skill = Skill(
                response_summary_id=response_summary.id,
                skill_name=skill_data.get("skill"),
                reason=skill_data.get("reason"),
                level_of_importance=skill_data.get("levelOfImportance"),
                match_label=skill_data.get("matchLabel"),
            )
            session.add(skill)
        session.commit()
        step_end_time = perf_counter()
        print(f"Step 2 (Save Skills): {step_end_time - step_start_time:.4f} seconds")

        # Step 3: Refresh the response_summary object
        step_start_time = perf_counter()
        session.refresh(response_summary)
        step_end_time = perf_counter()
        print(f"Step 3 (Refresh ResponseSummary): {step_end_time - step_start_time:.4f} seconds")

        # Total time
        total_end_time = perf_counter()
        print(f"Total Time Taken: {total_end_time - total_start_time:.4f} seconds")

        return response_summary.id
    except Exception as e:
        session.rollback()
        print(f"Error saving OpenAI response: {e}")
        raise
    finally:
        session.close()
