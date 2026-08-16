"""Tests de contrato HTTP para `/api/v1/*`. No validan valores de negocio
(eso ya lo hacen test_pattern_service.py y test_risk_service.py sobre las
funciones puras) — validan que los endpoints respondan con la forma
esperada sobre el `dashboard/data.json` real del entorno donde corren."""
import os

os.environ.setdefault("DESHABILITAR_SCHEDULER", "true")

import pytest
from fastapi.testclient import TestClient

from api.main import app


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_contratos_bloques_tiene_las_claves_nuevas(client):
    r = client.get("/api/v1/contratos")
    assert r.status_code == 200
    claves = set(r.json().keys())
    esperadas = {
        "hhi_por_organismo", "concentracion_top3", "concentracion_top5",
        "redes", "patrones", "riesgo_ircs",
    }
    assert esperadas <= claves


def test_contratos_bloque_desconocido_da_404(client):
    r = client.get("/api/v1/contratos/no_existe")
    assert r.status_code == 404


def test_patrones_reglas_devuelve_las_8_reglas(client):
    r = client.get("/api/v1/patrones/reglas")
    assert r.status_code == 200
    assert len(r.json()) == 8


def test_riesgo_ircs_post_calcula_score(client):
    r = client.post("/api/v1/riesgo/ircs", json={"concentracion": 100, "redes": 100})
    assert r.status_code == 200
    assert r.json()["ircs"] == 100.0


def test_empresa_inexistente_devuelve_disponible_false(client):
    r = client.get("/api/v1/empresas/NO_EXISTE")
    assert r.status_code == 200
    assert r.json()["disponible"] is False


def test_alertas_responde_con_forma_esperada(client):
    r = client.get("/api/v1/alertas")
    assert r.status_code == 200
    cuerpo = r.json()
    assert set(cuerpo.keys()) == {"disponible", "cantidad", "alertas"}


def test_endpoints_heredados_siguen_funcionando(client):
    """Compatibilidad hacia atrás: el hub Mapa de Transparencia consume
    estos endpoints sin prefijo (ver README); no se movieron."""
    assert client.get("/indicadores/macro").status_code == 200
    assert client.get("/scoring/reglas").status_code == 200
    assert client.get("/procurement/hhi_por_organismo").status_code == 200


def test_documentos_procesar_extrae_entidades_reales(client):
    texto = "El MINISTERIO DE ECONOMIA, representado por el Dr. Juan Perez, firmó con EMPRESA XYZ S.A. (CUIT 30-71659554-9)."
    r = client.post("/api/v1/documentos/procesar", json={"texto": texto, "documento": "Decreto 1/2026"})
    assert r.status_code == 200
    cuerpo = r.json()
    assert cuerpo["documento"] == "Decreto 1/2026"
    tipos = {e["tipo"] for e in cuerpo["entidades"]}
    assert "cuit" in tipos
    assert "organismo" in tipos
