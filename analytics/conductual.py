"""Capa 3 — Diagnóstico Conductual y Compliance (Behavioral Insights).

Implementa el Índice de Fricción Burocrática (Sludge Index) y la
verificación de Integridad Corporativa (MEACI Audit), sobre datos reales
de trámites/expedientes y auditorías de compliance.

Metodología del Sludge Index (ver World Bank, "Using Behavioral Insights
to Fight Corruption", GIUP/eMBeD): mide fricción anómala en trámites
comparando el tiempo real de procesamiento contra el tiempo normativo/
esperado, y la dispersión entre organismos/agentes que tramitan el mismo
tipo de expediente. Una fricción sistemáticamente alta en ciertos nodos
(dependencias, agentes) es consistente con demoras intencionales que
incentivan pagos de agilización ("peajes").
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def sludge_index(
    tramites: pd.DataFrame,
    tiempo_normativo_dias: dict[str, float] | None = None,
) -> pd.DataFrame:
    """`tramites` (datos reales de gestión de expedientes) requiere:
    tipo_tramite, organismo, dependencia, dias_transcurridos.

    Para cada (organismo, dependencia, tipo_tramite):
      - exceso_promedio = tiempo_real_promedio - tiempo_normativo
      - dispersión (std) como proxy de trato discrecional/no estandarizado
      - sludge_score = combinación normalizada de ambos (0-100)
    """
    tiempo_normativo_dias = tiempo_normativo_dias or {}

    resumen = (
        tramites.groupby(["organismo", "dependencia", "tipo_tramite"])["dias_transcurridos"]
        .agg(tiempo_promedio="mean", desvio="std", n_tramites="count")
        .reset_index()
    )
    resumen["tiempo_normativo"] = resumen["tipo_tramite"].map(tiempo_normativo_dias)
    resumen["exceso_dias"] = resumen["tiempo_promedio"] - resumen["tiempo_normativo"]

    # Normalización simple 0-100 sobre el exceso y la dispersión observados
    def normalizar(serie: pd.Series) -> pd.Series:
        rango = serie.max() - serie.min()
        return ((serie - serie.min()) / rango * 100) if rango > 0 else pd.Series(0.0, index=serie.index)

    resumen["exceso_norm"] = normalizar(resumen["exceso_dias"].clip(lower=0).fillna(0))
    resumen["desvio_norm"] = normalizar(resumen["desvio"].fillna(0))
    resumen["sludge_score"] = (0.7 * resumen["exceso_norm"] + 0.3 * resumen["desvio_norm"]).round(2)

    return resumen.sort_values("sludge_score", ascending=False)


def meaci_audit_score(auditorias: pd.DataFrame) -> pd.DataFrame:
    """Consolida auditorías reales de programas de integridad (Ley 27.401)
    por empresa. Distingue "compliance de papel" (programa declarado sin
    score de efectividad real) de programas auditados con score alto.
    `auditorias` (tabla `auditoria_compliance`) requiere: empresa_id,
    tiene_programa_integridad, score_efectividad, fecha."""
    resumen = (
        auditorias.sort_values("fecha")
        .groupby("empresa_id")
        .agg(
            ultima_auditoria=("fecha", "max"),
            tiene_programa=("tiene_programa_integridad", "last"),
            score_efectividad=("score_efectividad", "last"),
            n_auditorias=("fecha", "count"),
        )
        .reset_index()
    )
    resumen["compliance_de_papel"] = resumen["tiene_programa"] & (
        resumen["score_efectividad"].fillna(0) < 40
    )
    return resumen.sort_values(["compliance_de_papel", "score_efectividad"], ascending=[False, True])


def expectativas_informales(
    encuestas_experiencia_usuario: pd.DataFrame,
) -> pd.DataFrame:
    """Cruza percepción ciudadana de fricción (report cards / encuestas
    reales de experiencia en trámites) con la dependencia correspondiente,
    para contrastar contra el `sludge_index` calculado desde datos
    administrativos. `encuestas_experiencia_usuario` requiere: dependencia,
    percepcion_agilizacion_informal (0-10), n_respuestas."""
    resumen = (
        encuestas_experiencia_usuario.groupby("dependencia")
        .apply(
            lambda g: np.average(
                g["percepcion_agilizacion_informal"], weights=g["n_respuestas"]
            )
        )
        .rename("percepcion_ponderada")
        .reset_index()
    )
    return resumen.sort_values("percepcion_ponderada", ascending=False)
