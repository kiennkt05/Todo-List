from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import DeclarativeBase, sessionmaker


class Base(DeclarativeBase):
    pass


def build_database(url: str) -> tuple[Engine, sessionmaker]:
    parsed = make_url(url)
    if parsed.drivername.startswith("sqlite") and parsed.database not in (None, ":memory:"):
        Path(parsed.database).parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(
        url,
        connect_args={"check_same_thread": False} if parsed.drivername.startswith("sqlite") else {},
    )
    return engine, sessionmaker(bind=engine, expire_on_commit=False)
