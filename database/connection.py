"""Conexión SQLAlchemy a Postgres (ver db/schema.sql y config/settings.py).

El motor de conexión se crea de forma perezosa: importar este módulo no
intenta conectarse a una base que puede no estar disponible (ej. corriendo
el pipeline solo con CSV, o durante tests que no la necesitan)."""
from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from config.settings import SETTINGS

_engine: Engine | None = None
_SessionLocal: sessionmaker | None = None


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        _engine = create_engine(SETTINGS.db.dsn, pool_pre_ping=True, future=True)
    return _engine


def get_sessionmaker() -> sessionmaker:
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(bind=get_engine(), expire_on_commit=False, future=True)
    return _SessionLocal


@contextmanager
def sesion() -> Iterator[Session]:
    """Context manager de una sesión real: hace commit si todo sale bien,
    rollback si algo lanza excepción, y siempre cierra la conexión."""
    SessionLocal = get_sessionmaker()
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def verificar_conexion() -> bool:
    """True si se puede abrir una conexión real contra Postgres ahora
    mismo. No lanza excepción — se usa para decidir, en caliente, si
    `pipeline.py` persiste en la base o sigue solo con
    `dashboard/data.json` (misma filosofía que la ingesta de indicadores
    macro cayendo a valores de referencia si la API no responde)."""
    try:
        with get_engine().connect():
            return True
    except Exception:
        return False
