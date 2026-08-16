"""Tests de la capa de persistencia (`database/`) contra un Postgres real
con `db/schema.sql` aplicado — no contra mocks, porque lo que importa acá
es que el ORM y los repositorios calcen con el esquema real.

Se saltean automáticamente si no hay un Postgres disponible en
`TEST_DATABASE_DSN` (o el default de abajo, pensado para levantar uno
rápido en local: `docker compose up -d` ya deja el esquema aplicado, o
`createdb` a mano + `psql -f db/schema.sql`). No dependen de
`config/settings.py` ni de variables `PG_*` para no interferir con el
resto de la suite, que no necesita Postgres."""
from __future__ import annotations

import os

import pandas as pd
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from database.models import Entidad, GrafoArista, IndicadorMacro, Licitacion, ScoreRiesgo
from database import repositories as db_repo

TEST_DSN = os.environ.get(
    "TEST_DATABASE_DSN", "postgresql+psycopg2://corrupcion_test:test@localhost:5432/corrupcion_test"
)


def _postgres_disponible() -> bool:
    try:
        with create_engine(TEST_DSN).connect():
            return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _postgres_disponible(),
    reason=f"Postgres no disponible en TEST_DATABASE_DSN ({TEST_DSN}); se saltean los tests de database/",
)


@pytest.fixture()
def session():
    """Una sesión real contra Postgres, dentro de una transacción que
    nunca se commitea — así cada test queda aislado sin tener que
    limpiar la tabla a mano."""
    engine = create_engine(TEST_DSN, future=True)
    Session = sessionmaker(bind=engine, future=True)
    s = Session()
    try:
        yield s
    finally:
        s.rollback()
        s.close()


def test_obtener_o_crear_entidad_es_idempotente_por_identificador_fiscal(session):
    a = db_repo.obtener_o_crear_entidad(session, "Empresa X", "EMPRESA", "test", identificador_fiscal="30-1-1")
    b = db_repo.obtener_o_crear_entidad(session, "Empresa X (nombre distinto)", "EMPRESA", "test", identificador_fiscal="30-1-1")
    assert a.entidad_id == b.entidad_id


def test_upsert_entidades_de_licitaciones_crea_organismos_y_empresas(session):
    licitaciones = pd.DataFrame({
        "licitacion_id": ["L1", "L2"],
        "organismo": ["ORG_TEST_DB", "ORG_TEST_DB"],
        "proveedor": ["EMPRESA_TEST_DB_A", "EMPRESA_TEST_DB_B"],
        "monto_adjudicado": [100.0, 200.0],
    })
    mapa = db_repo.upsert_entidades_de_licitaciones(session, licitaciones)
    assert mapa["ORG_TEST_DB"].tipo == "ORGANISMO_PUBLICO"
    assert mapa["EMPRESA_TEST_DB_A"].tipo == "EMPRESA"
    assert mapa["EMPRESA_TEST_DB_B"].tipo == "EMPRESA"


def test_persistir_licitaciones_es_idempotente_por_fuente_id_externo(session):
    licitaciones = pd.DataFrame({
        "licitacion_id": ["L1"],
        "organismo": ["ORG_TEST_DB2"],
        "proveedor": ["EMPRESA_TEST_DB2"],
        "monto_adjudicado": [100.0],
        "fecha_adjudicacion": ["2024-01-01"],
    })
    entidades = db_repo.upsert_entidades_de_licitaciones(session, licitaciones)

    mapa_1 = db_repo.persistir_licitaciones(session, licitaciones, entidades)
    licitaciones.loc[0, "monto_adjudicado"] = 999.0
    mapa_2 = db_repo.persistir_licitaciones(session, licitaciones, entidades)

    assert mapa_1["L1"].licitacion_id == mapa_2["L1"].licitacion_id  # mismo registro, no un duplicado
    assert float(mapa_2["L1"].monto_adjudicado) == 999.0  # se actualizó in place

    total = session.execute(
        select(Licitacion).where(Licitacion.fuente_id_externo == "L1")
    ).scalars().all()
    assert len(total) == 1


def test_persistir_indicadores_macro_es_idempotente(session):
    indicadores = [{"pais_iso3": "TST", "anio": 2099, "indicador": "CPI", "valor": 50, "fuente": "test"}]
    db_repo.persistir_indicadores_macro(session, indicadores)
    db_repo.persistir_indicadores_macro(session, [{**indicadores[0], "valor": 60}])

    filas = session.execute(
        select(IndicadorMacro).where(IndicadorMacro.pais_iso3 == "TST", IndicadorMacro.anio == 2099)
    ).scalars().all()
    assert len(filas) == 1
    assert float(filas[0].valor) == 60.0


def test_persistir_grafo_aristas_y_scores_riesgo(session):
    licitaciones = pd.DataFrame({
        "licitacion_id": ["L1"],
        "organismo": ["ORG_TEST_DB3"],
        "proveedor": ["EMPRESA_TEST_DB3"],
        "monto_adjudicado": [100.0],
    })
    entidades = db_repo.upsert_entidades_de_licitaciones(session, licitaciones)
    licitaciones_map = db_repo.persistir_licitaciones(session, licitaciones, entidades)

    aristas = pd.DataFrame({"origen_id": ["ORG_TEST_DB3"], "destino_id": ["EMPRESA_TEST_DB3"], "peso": [100.0]})
    n_aristas = db_repo.persistir_grafo_aristas(session, aristas, entidades)
    assert n_aristas == 1
    assert session.execute(select(GrafoArista)).scalars().first() is not None

    tabla_ircs = pd.DataFrame({"licitacion_id": ["L1"], "ircs": [72.5], "ircs_componentes": [{"concentracion": 100}]})
    n_scores = db_repo.persistir_scores_riesgo(session, tabla_ircs, licitaciones_map)
    assert n_scores == 1
    # persistir_scores_riesgo NO es idempotente a propósito (queda como
    # historial de corridas sucesivas, ver docstring) — se verifica que
    # el score nuevo esté presente, no que sea el único para esa licitación.
    scores = session.execute(
        select(ScoreRiesgo).where(ScoreRiesgo.licitacion_id == licitaciones_map["L1"].licitacion_id)
    ).scalars().all()
    assert any(float(s.score) == 72.5 for s in scores)
