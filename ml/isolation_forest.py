"""Isolation Forest sobre las features reales de cada licitación (monto,
cantidad_ofertas, duracion, modificaciones, proveedor_participacion).
Devuelve un score de anomalía normalizado a [0, 1] por fila (más alto =
más atípico dentro de la propia corrida) — no una clasificación binaria;
la interpretación final (nivel, factores) queda en `ml/scoring.py`.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest

COLUMNAS_FEATURES = ["monto", "cantidad_ofertas", "duracion", "modificaciones", "proveedor_participacion"]

# Isolation Forest necesita más de un puñado de filas para que el
# "aislamiento" tenga algún sentido estadístico; por debajo de esto,
# services/risk_service.py cae al heurístico z-score.
MIN_FILAS = 4


def calcular_anomaly_score(features: pd.DataFrame, random_state: int = 42) -> pd.Series:
    """`features` debe tener las columnas de `COLUMNAS_FEATURES` ya
    imputadas (sin NaN) — ver `ml.scoring.construir_features`. Devuelve
    un score en [0, 1] por fila, indexado igual que `features`."""
    if len(features) < MIN_FILAS:
        return pd.Series(np.nan, index=features.index)

    modelo = IsolationForest(n_estimators=200, contamination="auto", random_state=random_state)
    modelo.fit(features[COLUMNAS_FEATURES])

    # score_samples: más alto = más "normal" para el modelo. Se invierte
    # y se normaliza contra el rango observado en esta misma corrida
    # (el objetivo es un ranking relativo dentro del propio dataset
    # provisto, no un umbral absoluto entrenado en otro contexto).
    bruto = -modelo.score_samples(features[COLUMNAS_FEATURES])
    minimo, maximo = bruto.min(), bruto.max()
    if maximo == minimo:
        return pd.Series(0.0, index=features.index)
    return pd.Series((bruto - minimo) / (maximo - minimo), index=features.index)
