"""Capa de persistencia real contra Postgres (`db/schema.sql`).

- `connection.py`    Motor/sesión SQLAlchemy, creados de forma perezosa.
- `models.py`         ORM declarativo (SQLAlchemy 2.0) que mapea las tablas reales del esquema.
- `repositories.py`   Funciones de upsert idempotentes usadas por `pipeline.py`.

Nota sobre nombres: el paquete `models/` (en la raíz del repo) son
modelos Pydantic para la superficie de la API (`api/v1/`) — ver
`models/__init__.py`. `database/models.py` son modelos ORM de SQLAlchemy
para la persistencia. Son dos cosas distintas a propósito (I/O de la API
vs. filas reales de la base), aunque el nombre "models" se repita; es el
mismo patrón que usa la documentación oficial de FastAPI en su tutorial
de SQL (`models.py` para SQLAlchemy, `schemas.py` para Pydantic).

Conectarse a Postgres es opcional: si no hay una base disponible (o las
credenciales de `config/settings.py` no resuelven), `pipeline.py` sigue
funcionando igual y solo persiste en `dashboard/data.json`, igual que ya
hace con la ingesta de indicadores macro cuando la API del Banco Mundial
no responde. Ver `connection.verificar_conexion()`.
"""
