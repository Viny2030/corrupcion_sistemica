"""Tests del Motor A (ml/scoring.py). Ejemplo mínimo de laboratorio: 4
licitaciones "normales" y 1 con un monto muy por fuera del resto — no
simula corrupción real, solo verifica que el score de anomalía la
identifique como la más atípica del lote (requisito mínimo para
cualquiera de los 3 algoritmos que se combinan)."""
import pandas as pd
import pytest

from ml import scoring as ml_scoring
from ml.isolation_forest import MIN_FILAS


def _licitaciones_con_un_outlier():
    return pd.DataFrame(
        {
            "licitacion_id": ["L1", "L2", "L3", "L4", "L5"],
            "organismo": ["ORG_A"] * 5,
            "proveedor": ["X", "Y", "Z", "W", "V"],
            "monto_adjudicado": [100.0, 105.0, 98.0, 102.0, 100000.0],
            "fecha_apertura": ["2024-01-01"] * 5,
            "fecha_adjudicacion": ["2024-01-15"] * 5,
        }
    )


def test_calcular_anomalias_identifica_el_outlier_como_el_mas_atipico():
    tabla = ml_scoring.calcular_anomalias(_licitaciones_con_un_outlier())
    assert not tabla.empty
    top = tabla.iloc[0]
    assert top["licitacion_id"] == "L5"
    assert top["anomaly_score"] > tabla.iloc[1]["anomaly_score"]
    assert "monto_atipico" in top["factores"]
    assert top["nivel"] in ("alto", "medio")


def test_calcular_anomalias_devuelve_vacio_con_pocas_filas():
    pocas = _licitaciones_con_un_outlier().head(MIN_FILAS - 1)
    tabla = ml_scoring.calcular_anomalias(pocas)
    assert tabla.empty


def test_calcular_anomalias_con_licitaciones_vacias_no_rompe():
    vacio = pd.DataFrame(columns=["licitacion_id", "organismo", "proveedor", "monto_adjudicado"])
    tabla = ml_scoring.calcular_anomalias(vacio)
    assert tabla.empty


def test_construir_features_no_deja_nan():
    features = ml_scoring.construir_features(_licitaciones_con_un_outlier())
    assert not features[ml_scoring.COLUMNAS_FEATURES].isna().any().any()


def test_risk_service_usa_motor_ml_con_filas_suficientes():
    from services import risk_service

    tabla = risk_service.componente_anomalias(_licitaciones_con_un_outlier())
    assert not tabla.empty
    assert "factores" in tabla.columns  # el heurístico también expone la columna, mismo contrato


def test_risk_service_cae_a_heuristico_con_pocas_filas():
    from services import risk_service

    pocas = _licitaciones_con_un_outlier().head(MIN_FILAS - 1)
    tabla = risk_service.componente_anomalias(pocas)
    assert not tabla.empty
    assert tabla.iloc[0]["licitacion_id"] in pocas["licitacion_id"].values
