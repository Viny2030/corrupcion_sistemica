"""Resolución de entidades (Entity Resolution).

Agrupa empresas aparentemente independientes (SA, UTE, SRL) que en
realidad comparten estructura real: domicilio, email en pliegos,
directorio/apoderados, representante técnico o balances. Usa fuzzy
matching real (rapidfuzz) sobre los campos de la tabla `entidad`
poblada con datos reales.
"""

from __future__ import annotations

from itertools import combinations

import pandas as pd
from rapidfuzz import fuzz

UMBRAL_SIMILITUD_TEXTO = 90  # 0-100, score de rapidfuzz


def _similares_por_campo(entidades: pd.DataFrame, campo: str, umbral: int = UMBRAL_SIMILITUD_TEXTO) -> pd.DataFrame:
    filas = entidades.dropna(subset=[campo])[["entidad_id", campo]].values.tolist()
    resultados = []
    for (id_a, val_a), (id_b, val_b) in combinations(filas, 2):
        if id_a == id_b:
            continue
        score = fuzz.token_sort_ratio(str(val_a).lower(), str(val_b).lower())
        if score >= umbral:
            resultados.append(
                {
                    "entidad_id": id_a,
                    "entidad_relacionada_id": id_b,
                    "metodo": campo,
                    "score_similitud": round(score / 100, 4),
                }
            )
    return pd.DataFrame(resultados)


def resolver_entidades(entidades: pd.DataFrame) -> pd.DataFrame:
    """`entidades` (tabla real `entidad`) debe incluir, cuando existan,
    columnas: domicilio, email_pliego, directorio, representante_tecnico,
    balance_hash (o similar). Devuelve candidatos a fusión con evidencia
    del método que los vinculó (para la tabla `entidad_alias`)."""
    campos_evidencia = [
        c for c in ["domicilio", "email_pliego", "directorio", "representante_tecnico", "balance_hash"]
        if c in entidades.columns
    ]
    if not campos_evidencia:
        return pd.DataFrame(columns=["entidad_id", "entidad_relacionada_id", "metodo", "score_similitud"])

    partes = [_similares_por_campo(entidades, campo) for campo in campos_evidencia]
    partes = [p for p in partes if not p.empty]
    if not partes:
        return pd.DataFrame(columns=["entidad_id", "entidad_relacionada_id", "metodo", "score_similitud"])
    return pd.concat(partes, ignore_index=True).sort_values("score_similitud", ascending=False)


def consolidar_grupos(candidatos: pd.DataFrame) -> pd.DataFrame:
    """Agrupa pares transitivos (A~B, B~C => {A,B,C}) en un mismo
    'grupo_real' usando componentes conexas simples (sin dependencias
    externas de grafos, solo unión de conjuntos)."""
    if candidatos.empty:
        return pd.DataFrame(columns=["entidad_id", "grupo_real"])

    padre: dict[str, str] = {}

    def find(x: str) -> str:
        padre.setdefault(x, x)
        while padre[x] != x:
            x = padre[x]
        return x

    def union(x: str, y: str) -> None:
        rx, ry = find(x), find(y)
        if rx != ry:
            padre[rx] = ry

    for _, fila in candidatos.iterrows():
        union(fila["entidad_id"], fila["entidad_relacionada_id"])

    grupos = {nodo: find(nodo) for nodo in padre}
    return pd.DataFrame(list(grupos.items()), columns=["entidad_id", "grupo_real"])
