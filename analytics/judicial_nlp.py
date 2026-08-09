"""Capa 4 — Vaciamiento Institucional y Control Judicial.

Indicadores sobre datos reales de causas judiciales (tabla
`causa_judicial` + `imputado`) obtenidos vía ingestion/judicial_saij.py,
y sobre votaciones legislativas cruzadas con contrataciones.
"""

from __future__ import annotations

import re

import pandas as pd

# Léxico base para el análisis de severidad de sentencias. En un despliegue
# real se recomienda reemplazar/ampliar este diccionario con un modelo de
# clasificación entrenado (ej. spaCy fine-tuned) sobre un corpus etiquetado
# de fallos reales; aquí se deja una heurística transparente y auditable
# como punto de partida reproducible.
TERMINOS_SEVERIDAD_ALTA = [
    r"prisión efectiva", r"pena de prisión", r"inhabilitaci[oó]n perpetua",
    r"decomiso", r"reclusi[oó]n",
]
TERMINOS_SEVERIDAD_BAJA = [
    r"probation", r"suspensi[oó]n del juicio a prueba", r"multa",
    r"absoluci[oó]n", r"sobreseimiento",
]


def tasa_extincion_por_prescripcion(causas: pd.DataFrame) -> pd.DataFrame:
    """Porcentaje de expedientes de corrupción que se extinguen por
    prescripción, agrupado por fuero/jurisdicción. `causas` (tabla
    `causa_judicial`) requiere: fuero, jurisdiccion, estado."""
    resumen = (
        causas.groupby(["fuero", "jurisdiccion"])
        .agg(
            total_causas=("causa_id", "count"),
            prescriptas=("estado", lambda s: (s == "PRESCRIPTA").sum()),
        )
        .reset_index()
    )
    resumen["tasa_prescripcion_pct"] = (
        resumen["prescriptas"] / resumen["total_causas"] * 100
    ).round(2)
    return resumen.sort_values("tasa_prescripcion_pct", ascending=False)


def _clasificar_severidad(texto: str) -> str:
    texto = (texto or "").lower()
    if any(re.search(p, texto) for p in TERMINOS_SEVERIDAD_ALTA):
        return "ALTA"
    if any(re.search(p, texto) for p in TERMINOS_SEVERIDAD_BAJA):
        return "BAJA"
    return "INDETERMINADA"


def sesgo_de_sancion(causas: pd.DataFrame, imputados: pd.DataFrame) -> pd.DataFrame:
    """Analiza si las condenas severas recaen desproporcionadamente en
    mandos bajos/medios, dejando indemnes a las cúpulas. Combina
    clasificación de severidad textual (NLP sobre `texto_fallo`, real,
    heurístico y auditable) con el `rango_jerarquico` real del imputado.

    `causas` requiere: causa_id, texto_fallo.
    `imputados` requiere: causa_id, entidad_id, rango_jerarquico, condena_meses.
    """
    causas = causas.copy()
    causas["severidad_texto"] = causas["texto_fallo"].apply(_clasificar_severidad)

    df = imputados.merge(causas[["causa_id", "severidad_texto"]], on="causa_id", how="left")

    resumen = (
        df.groupby("rango_jerarquico")
        .agg(
            n_imputados=("entidad_id", "count"),
            condena_meses_promedio=("condena_meses", "mean"),
            pct_severidad_alta=("severidad_texto", lambda s: (s == "ALTA").mean() * 100),
        )
        .reset_index()
    )
    return resumen.sort_values("condena_meses_promedio", ascending=False)


def matriz_voto_contrato(
    votos: pd.DataFrame, licitaciones: pd.DataFrame, empresas_relacionadas: pd.DataFrame
) -> pd.DataFrame:
    """Cruza votos legislativos favorables a normativa/presupuesto sectorial
    con contrataciones posteriores obtenidas por empresas vinculadas al
    legislador (vía `empresas_relacionadas`: legislador_id, empresa_id,
    tipo_vinculo — ej. familiar, ex-socio, declarado en DDJJ).

    `votos` requiere: legislador_id, votacion_id, voto, fecha.
    `licitaciones` requiere: proveedor(empresa_id), fecha_adjudicacion, monto_adjudicado.
    """
    votos_favorables = votos[votos["voto"] == "AFIRMATIVO"]
    cruce = votos_favorables.merge(empresas_relacionadas, on="legislador_id", how="inner")
    cruce = cruce.merge(
        licitaciones, left_on="empresa_id", right_on="proveedor", how="inner"
    )
    cruce = cruce[cruce["fecha_adjudicacion"] >= cruce["fecha"]]

    resumen = (
        cruce.groupby(["legislador_id", "empresa_id", "tipo_vinculo"])
        .agg(
            n_votos_favorables=("votacion_id", "nunique"),
            monto_adjudicado_posterior=("monto_adjudicado", "sum"),
        )
        .reset_index()
    )
    return resumen.sort_values("monto_adjudicado_posterior", ascending=False)
