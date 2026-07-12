import os

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from collections.abc import Generator

from sqlalchemy.orm import Session

DATABASE_URL = os.environ["DATABASE_URL"]

# pool_pre_ping avoids stale connections when Docker containers cycle
engine = create_engine(DATABASE_URL, pool_pre_ping=True)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


# Every model inherits from this. It's the registry that ties Python
# classes to their database tables.
class Base(DeclarativeBase):
    pass

def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()