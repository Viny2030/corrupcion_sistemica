"""Índice de Riesgo de Corrupción Sistémica (IRCS), 0-100.

    IRCS = 20% anomalías + 20% concentración + 20% redes + 15% patrones
         + 15% opacidad + 10% institucional

Cada componente se normaliza a 0-100 a partir de una métrica real ya
calculada por otro módulo — no hay ningún número inventado:

- **anomalías**: Motor A real (`ml/scoring.py`: Isolation Forest + LOF +
  DBSCAN) cuando hay licitaciones suficientes para entrenar
  (`ml.isolation_forest.MIN_FILAS`); si no, cae automáticamente al
  heurístico estadístico (z-score sobre el monto adjudicado) como
  respaldo transparente — ver `componente_anomalias` más abajo.
- **concentración**: `analytics/finanzas.hhi_por_organismo` (HHI/100).
- **redes**: `services/network_service` (`network_score`, ya 0-100).
- **patrones**: `services/pattern_service` (`score_patrones`, ya 0-100).
- **opacidad**: % de campos clave de la licitación con datos reales
  ausentes (evidencia declarada, no un juicio de valor).
- **institucional**: CPI / WGI Control de Corrupción reales, ya
  ingeridos por `pipeline.ingerir_indicadores_macro()`, invertidos para
  que "más corrupción percibida en el país" => IRCS institucional más
  alto.

IMPORTANTE: el resultado es un score de RIESGO, no una acusación ni una
prueba de delito. Un IRCS alto señala dónde mirar con más atención, no
concluye responsabilidad — eso lo determina una investigación real.
"""
from __future__ import annotations

from typing import Optional

import pandas as pd

PESOS = {
    "anomalias": 0.20,
    "concentracion": 0.20,
    "redes": 0.20,
    "patrones": 0.15,
    "opacidad": 0.15,
    "institucional": 0.10,
}

CAMPOS_CLAVE_OPACIDAD = [
    "presupuesto_oficial", "monto_adjudicado", "fecha_apertura",
    "fecha_adjudicacion", "modalidad", "rubro",
]


def _nivel(score: float) -> str:
    if score >= 75:
        return "ALTO"
    if score >= 50:
        return "MEDIO"
    return "BAJO"


def _componente_anomalias_heuristico(licitaciones: pd.DataFrame) -> pd.DataFrame:
    """Heurística de respaldo (z-score sobre el monto adjudicado): se usa
    cuando el Motor A (`ml/scoring.py`) no puede correr — scikit-learn no
    instalado, o menos de `ml.isolation_forest.MIN_FILAS` licitaciones
    para entrenar. Es una señal real calculada sobre los datos provistos,
    no un valor simulado, aunque mucho más simple que Isolation Forest/
    LOF/DBSCAN."""
    columnas = ["licitacion_id", "anomaly_score", "nivel", "factores"]
    if licitaciones.empty or "monto_adjudicado" not in licitaciones.columns:
        return pd.DataFrame(columns=columnas)

    df = licitaciones.copy()
    media = df["monto_adjudicado"].mean()
    desvio = df["monto_adjudicado"].std(ddof=0) or 0.0
    df["z_monto"] = 0.0 if desvio == 0 else (df["monto_adjudicado"] - media) / desvio
    df["anomaly_score"] = (df["z_monto"].abs().clip(upper=3) / 3 * 100).round(2)
    df["nivel"] = df["anomaly_score"].apply(lambda s: "alto" if s >= 75 else "medio" if s >= 40 else "bajo")
    df["factores"] = df["z_monto"].apply(lambda z: ["monto_atipico"] if abs(z) > 1.5 else [])
    return df[["licitacion_id", "anomaly_score", "nivel", "factores"]]


def componente_anomalias(
    licitaciones: pd.DataFrame,
    ofertas: Optional[pd.DataFrame] = None,
    adendas: Optional[pd.DataFrame] = None,
) -> pd.DataFrame:
    """Motor A real (`ml/scoring.py`: Isolation Forest + LOF + DBSCAN)
    cuando hay filas suficientes para entrenar; si no —o si scikit-learn
    no está instalado—, cae a `_componente_anomalias_heuristico` como
    respaldo transparente. Devuelve `licitacion_id`, `anomaly_score`
    (0-100), `nivel` y `factores` en ambos casos, para que
    `GET /api/v1/contratos/anomalias` tenga siempre la misma forma sin
    importar qué motor se usó."""
    try:
        from ml import scoring as ml_scoring
    except ImportError:  # scikit-learn no instalado en este entorno
        return _componente_anomalias_heuristico(licitaciones)

    avanzado = ml_scoring.calcular_anomalias(licitaciones, ofertas, adendas)
    if not avanzado.empty:
        return avanzado
    return _componente_anomalias_heuristico(licitaciones)


def componente_opacidad(licitaciones: pd.DataFrame, campos: list[str] = CAMPOS_CLAVE_OPACIDAD) -> pd.DataFrame:
    """Opacidad = % de campos clave sin dato real. 0 = expediente
    completo/transparente; 100 = ningún campo clave publicado."""
    if licitaciones.empty:
        return pd.DataFrame(columns=["licitacion_id", "opacidad_score"])

    df = licitaciones.copy()
    campos_presentes = [c for c in campos if c in df.columns]
    if not campos_presentes:
        df["opacidad_score"] = 100.0
    else:
        faltantes = df[campos_presentes].isna().sum(axis=1)
        df["opacidad_score"] = (faltantes / len(campos_presentes) * 100).round(2)

    columnas = ["licitacion_id", "opacidad_score"] if "licitacion_id" in df.columns else ["opacidad_score"]
    return df[columnas]


def componente_institucional(indicadores_macro: list[dict], pais_iso3: str = "ARG") -> float:
    """CPI (0-100, más alto = menos corrupción percibida) y WGI Control
    de Corrupción (aprox. -2.5 a 2.5, más alto = mejor control) reales,
    ya ingeridos por `pipeline.ingerir_indicadores_macro()`. Se invierten
    para que un IRCS más alto siempre signifique más riesgo. Si no hay
    ningún indicador real disponible para el país, devuelve 50 (neutro),
    en vez de 0 o 100, para no sesgar el resultado en ninguna dirección
    con datos ausentes."""
    cpi = [d["valor"] for d in indicadores_macro if d.get("pais_iso3") == pais_iso3 and d.get("indicador") == "CPI"]
    wgi = [
        d["valor"] for d in indicadores_macro
        if d.get("pais_iso3") == pais_iso3 and d.get("indicador") == "WGI_CONTROL_CORRUPCION"
    ]

    componentes = []
    if cpi:
        componentes.append(max(0.0, min(100.0, 100 - float(cpi[-1]))))
    if wgi:
        valor = float(wgi[-1])
        componentes.append(max(0.0, min(100.0, (2.5 - valor) / 5 * 100)))

    return round(sum(componentes) / len(componentes), 2) if componentes else 50.0


def calcular_ircs(
    concentracion: Optional[float] = None,
    redes: Optional[float] = None,
    patrones: Optional[float] = None,
    anomalias: Optional[float] = None,
    opacidad: Optional[float] = None,
    institucional: Optional[float] = None,
) -> dict:
    """IRCS puntual a partir de los 6 componentes ya calculados (0-100
    cada uno). El componente sin evidencia real (`None`) se excluye y los
    pesos se redistribuyen proporcionalmente entre los disponibles, en
    vez de asumírsele un valor que distorsione el resultado."""
    valores = {
        "anomalias": anomalias, "concentracion": concentracion, "redes": redes,
        "patrones": patrones, "opacidad": opacidad, "institucional": institucional,
    }
    disponibles = {k: v for k, v in valores.items() if v is not None}
    if not disponibles:
        return {"ircs": None, "nivel": "SIN_DATOS", "componentes": valores}

    peso_total_disponible = sum(PESOS[k] for k in disponibles)
    ircs = sum(v * PESOS[k] for k, v in disponibles.items()) / peso_total_disponible
    ircs = round(min(max(ircs, 0.0), 100.0), 2)

    return {"ircs": ircs, "nivel": _nivel(ircs), "componentes": valores}


def calcular_ircs_por_licitacion(
    licitaciones: pd.DataFrame,
    concentracion_por_organismo: pd.DataFrame,
    red_por_entidad: pd.DataFrame,
    patrones_por_licitacion: pd.DataFrame,
    anomalias_por_licitacion: pd.DataFrame,
    indicadores_macro: list[dict],
) -> pd.DataFrame:
    """Arma el IRCS fila a fila combinando las salidas ya calculadas de
    `concentration_service`/`finanzas`, `network_service`,
    `pattern_service`, `componente_anomalias` (Motor A o heurístico) y
    los indicadores macro reales ya ingeridos. Recibe `anomalias_por_licitacion`
    ya calculada (en vez de recalcularla acá) para no entrenar el modelo
    de ML dos veces por corrida — `pipeline.py` la calcula una sola vez y
    la reusa tanto para el bloque `anomalias` como para el IRCS."""
    columnas_id = ["licitacion_id", "organismo"] + (["proveedor"] if "proveedor" in licitaciones.columns else [])
    if licitaciones.empty or "licitacion_id" not in licitaciones.columns:
        return pd.DataFrame(columns=columnas_id + ["ircs", "nivel_ircs", "ircs_componentes"])

    opacidad = componente_opacidad(licitaciones)
    institucional_score = componente_institucional(indicadores_macro)

    df = licitaciones[columnas_id].copy()
    if anomalias_por_licitacion is not None and not anomalias_por_licitacion.empty:
        df = df.merge(anomalias_por_licitacion[["licitacion_id", "anomaly_score"]], on="licitacion_id", how="left")
    else:
        df["anomaly_score"] = None
    df = df.merge(opacidad, on="licitacion_id", how="left")

    if not concentracion_por_organismo.empty and "hhi" in concentracion_por_organismo.columns:
        conc = concentracion_por_organismo[["organismo", "hhi"]].copy()
        conc["concentracion_score"] = (conc["hhi"] / 100).clip(upper=100)
        df = df.merge(conc[["organismo", "concentracion_score"]], on="organismo", how="left")
    else:
        df["concentracion_score"] = None

    if "proveedor" in df.columns and red_por_entidad is not None and not red_por_entidad.empty:
        red = red_por_entidad[["entity", "network_score"]].rename(columns={"entity": "proveedor"})
        df = df.merge(red, on="proveedor", how="left")
    else:
        df["network_score"] = None

    if patrones_por_licitacion is not None and not patrones_por_licitacion.empty and "score_patrones" in patrones_por_licitacion.columns:
        df = df.merge(patrones_por_licitacion[["licitacion_id", "score_patrones"]], on="licitacion_id", how="left")
    else:
        df["score_patrones"] = None

    df["institucional_score"] = institucional_score

    resultados = df.apply(
        lambda f: calcular_ircs(
            concentracion=f.get("concentracion_score"),
            redes=f.get("network_score"),
            patrones=f.get("score_patrones"),
            anomalias=f.get("anomaly_score"),
            opacidad=f.get("opacidad_score"),
            institucional=f.get("institucional_score"),
        ),
        axis=1,
    )
    df["ircs"] = resultados.apply(lambda r: r["ircs"])
    df["nivel_ircs"] = resultados.apply(lambda r: r["nivel"])
    df["ircs_componentes"] = resultados.apply(lambda r: r["componentes"])
    return df.sort_values("ircs", ascending=False, na_position="last")
