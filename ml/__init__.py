"""Motor A — detección de anomalías con Machine Learning no supervisado
real (Isolation Forest, Local Outlier Factor, DBSCAN) sobre las features
de cada licitación: monto, cantidad de ofertas, duración, modificaciones
contractuales y participación del proveedor.

- `isolation_forest.py`  Isolation Forest — score de anomalía en [0, 1].
- `clustering.py`        LOF (densidad local) + DBSCAN (voto de outlier).
- `scoring.py`           Combina los tres en `anomaly_score` 0-100 + `nivel`
                          + `factores` explicativos (vía z-score por
                          columna, ya que los 3 algoritmos de arriba no
                          son explicables por sí mismos).

Reemplaza al heurístico z-score que usaba
`services/risk_service.componente_anomalias` como MVP — ver ese módulo:
sigue usando el heurístico como respaldo automático cuando hay muy pocas
filas para entrenar (`isolation_forest.MIN_FILAS`) o si scikit-learn no
está instalado.
"""
