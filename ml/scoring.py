"""Motor A completo: combina Isolation Forest + LOF + DBSCAN en un
`anomaly_score` 0-100 por licitación, con `nivel` (alto/medio/bajo) y
`factores` explicativos — la parte auditable del score, calculada por
z-score por columna, ya que los tres algoritmos de arriba no son
explicables por sí mismos.

Formato de salida alineado al resto del motor analítico (0-100, igual
que concentración/redes/patrones/opacidad/institucional en
`services/risk_service.py`), a diferencia del ejemplo original en 0-1 —
elegido así por consistencia interna del proyecto, documentado acá.
"""
from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd

from ml.clustering import calcular_dbscan_outliers, calcular_lof_score
from ml.isolation_forest import COLUMNAS_FEATURES, MIN_FILAS, calcular_anomaly_score

UMBRAL_Z_FACTOR = 1.5  # |z| por encima de esto se reporta como "factor" explicativo
NIVELES = (("alto", 75.0), ("medio", 40.0))

ETIQUETAS_FACTORES = {
    "monto": "monto_atipico",
    "cantidad_ofertas": "baja_competencia",
    "duracion": "duracion_atipica",
    "modificaciones": "modificaciones_frecuentes",
    "proveedor_participacion": "alta_concentracion",
}


def _nivel(score_0_100: float) -> str:
    for nombre, umbral in NIVELES:
        if score_0_100 >= umbral:
            return nombre
    return "bajo"


def construir_features(
    licitaciones: pd.DataFrame,
    ofertas: Optional[pd.DataFrame] = None,
    adendas: Optional[pd.DataFrame] = None,
) -> pd.DataFrame:
    """Arma la tabla de features reales (monto, cantidad_ofertas,
    duracion, modificaciones, proveedor_participacion), reusando
    `services.pattern_service.construir_tabla_patrones` para
    cantidad_ofertas/cuota_dominante_pct en vez de recalcularlas.
    Import perezoso de `services` para evitar un ciclo de imports
    (services.risk_service importa `ml.scoring`)."""
    from services import pattern_service

    base = pattern_service.construir_tabla_patrones(licitaciones, ofertas, adendas)

    df = pd.DataFrame(index=base.index)
    df["licitacion_id"] = base["licitacion_id"]
    df["monto"] = pd.to_numeric(base.get("monto_adjudicado"), errors="coerce")

    if "fecha_apertura" in base.columns and "fecha_adjudicacion" in base.columns:
        apertura = pd.to_datetime(base["fecha_apertura"], errors="coerce")
        adjudicacion = pd.to_datetime(base["fecha_adjudicacion"], errors="coerce")
        df["duracion"] = (adjudicacion - apertura).dt.days
    else:
        df["duracion"] = np.nan

    df["cantidad_ofertas"] = pd.to_numeric(base.get("cantidad_ofertas"), errors="coerce")

    if adendas is not None and not adendas.empty and "licitacion_id" in adendas.columns:
        conteo = adendas.groupby("licitacion_id").size().rename("modificaciones")
        df = df.merge(conteo, left_on="licitacion_id", right_index=True, how="left")
    else:
        df["modificaciones"] = np.nan

    df["proveedor_participacion"] = pd.to_numeric(base.get("cuota_dominante_pct"), errors="coerce") / 100

    # Imputación explícita y documentada (no oculta): mediana de la
    # propia corrida para lo numérico ausente y, si ni eso hay
    # (columna entera vacía), 0 como último recurso para no romper el
    # entrenamiento.
    for columna in COLUMNAS_FEATURES:
        df[columna] = df[columna].fillna(df[columna].median()).fillna(0.0)

    return df


def _factores_por_fila(fila: pd.Series, medias: pd.Series, desvios: pd.Series) -> list[str]:
    factores = []
    for columna, etiqueta in ETIQUETAS_FACTORES.items():
        desvio = desvios.get(columna) or 0.0
        if desvio == 0:
            continue
        z = (fila[columna] - medias.get(columna, 0.0)) / desvio
        # cantidad_ofertas: lo atípico es tener MENOS ofertas que el
        # resto (baja competencia), no más — por eso se evalúa distinto
        # que las demás columnas (donde atípico es |z| grande en
        # cualquier dirección).
        atipico = (z < -UMBRAL_Z_FACTOR) if columna == "cantidad_ofertas" else (abs(z) > UMBRAL_Z_FACTOR)
        if atipico:
            factores.append(etiqueta)
    return factores


def calcular_anomalias(
    licitaciones: pd.DataFrame,
    ofertas: Optional[pd.DataFrame] = None,
    adendas: Optional[pd.DataFrame] = None,
) -> pd.DataFrame:
    """Motor A completo. Combina Isolation Forest (40%), LOF (40%) y el
    voto de DBSCAN (20%) en un `anomaly_score` 0-100, con `nivel` y
    `factores`. Devuelve vacío si hay menos de `MIN_FILAS` licitaciones
    (no tiene sentido estadístico entrenar con tan pocos datos) — en ese
    caso `services/risk_service.py` cae al heurístico z-score."""
    columnas_salida = ["licitacion_id", "anomaly_score", "nivel", "factores"]
    if licitaciones.empty or len(licitaciones) < MIN_FILAS:
        return pd.DataFrame(columns=columnas_salida)

    features = construir_features(licitaciones, ofertas, adendas)

    iso = calcular_anomaly_score(features)
    lof = calcular_lof_score(features)
    dbscan_outlier = calcular_dbscan_outliers(features)

    combinado = (0.4 * iso.fillna(0) + 0.4 * lof.fillna(0) + 0.2 * dbscan_outlier.fillna(0)) * 100

    medias = features[COLUMNAS_FEATURES].mean()
    desvios = features[COLUMNAS_FEATURES].std(ddof=0)

    salida = pd.DataFrame({"licitacion_id": features["licitacion_id"], "anomaly_score": combinado.round(2)})
    salida["nivel"] = salida["anomaly_score"].apply(_nivel)
    salida["factores"] = features.apply(lambda f: _factores_por_fila(f, medias, desvios), axis=1)
    return salida.sort_values("anomaly_score", ascending=False)
