"""Local Outlier Factor y DBSCAN sobre las mismas features que
`isolation_forest.py`, como señales complementarias: que dos algoritmos
no supervisados distintos coincidan en marcar una fila como atípica es
una evidencia más fuerte que la de uno solo."""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.cluster import DBSCAN
from sklearn.neighbors import LocalOutlierFactor
from sklearn.preprocessing import StandardScaler

from ml.isolation_forest import COLUMNAS_FEATURES, MIN_FILAS


def calcular_lof_score(features: pd.DataFrame) -> pd.Series:
    """Local Outlier Factor: densidad local relativa de cada fila
    respecto de sus vecinas. Devuelve un score en [0, 1] (más alto = más
    atípica respecto de su vecindario, a diferencia de Isolation Forest
    que mide aislamiento global)."""
    if len(features) < MIN_FILAS:
        return pd.Series(np.nan, index=features.index)

    n_vecinos = min(20, len(features) - 1)
    modelo = LocalOutlierFactor(n_neighbors=n_vecinos)
    modelo.fit_predict(features[COLUMNAS_FEATURES])
    bruto = -modelo.negative_outlier_factor_  # más alto = más atípico
    minimo, maximo = bruto.min(), bruto.max()
    if maximo == minimo:
        return pd.Series(0.0, index=features.index)
    return pd.Series((bruto - minimo) / (maximo - minimo), index=features.index)


def calcular_dbscan_outliers(features: pd.DataFrame) -> pd.Series:
    """DBSCAN: filas que quedan fuera de cualquier cluster denso
    (label == -1) se marcan como atípicas (1.0); el resto en 0.0. A
    diferencia de Isolation Forest/LOF no da un score continuo, así que
    se usa como voto binario adicional en `ml/scoring.py`. Las features
    se escalan (media 0, desvío 1) antes de correr DBSCAN porque, a
    diferencia de los otros dos algoritmos, es sensible a la escala de
    cada columna (monto vs. cantidad_ofertas tienen órdenes de magnitud
    muy distintos)."""
    if len(features) < MIN_FILAS:
        return pd.Series(np.nan, index=features.index)

    escalado = StandardScaler().fit_transform(features[COLUMNAS_FEATURES])
    min_samples = max(2, min(5, len(features) // 3))
    modelo = DBSCAN(eps=1.5, min_samples=min_samples)
    labels = modelo.fit_predict(escalado)
    return pd.Series((labels == -1).astype(float), index=features.index)
