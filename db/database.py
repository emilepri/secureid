"""Connexion à la base SQLite et création des tables."""

from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from db.models import Base


def get_engine(db_path: str | Path = "secureid.db") -> Engine:
    engine = create_engine(f"sqlite:///{db_path}")

    @event.listens_for(engine, "connect")
    def _enable_foreign_keys(dbapi_connection, _record):
        # SQLite ignore les clés étrangères sauf si on les active à chaque connexion
        dbapi_connection.execute("PRAGMA foreign_keys = ON")

    return engine


def init_db(engine: Engine) -> sessionmaker[Session]:
    """Crée les tables si besoin et retourne une fabrique de sessions."""
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)
