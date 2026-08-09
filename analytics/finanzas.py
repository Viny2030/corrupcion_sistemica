"""Capa 2 — Finanzas Públicas e Interacción Estado-Mercado.

Indicadores sobre datos reales de licitaciones, pagos TGN y aportes de
campaña (tablas `licitacion`, `pago_tgn`, `adenda`, `aporte_campana`).
"""

from __future__ import annotations

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# TGN Bias — priorización financiera en Tesorería
# ---------------------------------------------------------------------------

def tgn_bias(pagos: pd.DataFrame) -> pd.DataFrame:
    """Compara los días hábiles de pago de cada empresa contra el promedio
    del organismo pagador. `pagos` requiere: empresa_id, organismo_id,
    dias_habiles_pago."""
    promedio_organismo = pagos.groupby("organismo_id")["dias_habiles_pago"].mean().rename("promedio_organismo")
    df = pagos.merge(promedio_organismo, left_on="organismo_id", right_index=True)
    df["dias_vs_promedio"] = df["dias_habiles_pago"] - df["promedio_organismo"]

    resumen = (
        df.groupby(["empresa_id", "organismo_id"])
        .agg(
            dias_promedio_empresa=("dias_habiles_pago", "mean"),
            dias_promedio_organismo=("promedio_organismo", "mean"),
            n_pagos=("dias_habiles_pago", "count"),
        )
        .reset_index()
    )
    resumen["dias_ahorrados"] = resumen["dias_promedio_organismo"] - resumen["dias_promedio_empresa"]
    resumen["priorizacion_detectada"] = resumen["dias_ahorrados"] > 0
    return resumen.sort_values("dias_ahorrados", ascending=False)


# ---------------------------------------------------------------------------
# HHI — Índice de Concentración Presupuestaria (Herfindahl-Hirschman)
# ---------------------------------------------------------------------------

def hhi_por_organismo(licitaciones: pd.DataFrame, adjudicatario_col: str = "proveedor") -> pd.DataFrame:
    """HHI = suma de (cuota de mercado %)^2 por proveedor, dentro de cada
    organismo. Rango 0-10000; > 2500 se considera alta concentración según
    los umbrales estándar usados por autoridades de competencia."""
    resultados = []
    for organismo, grupo in licitaciones.groupby("organismo"):
        total = grupo["monto_adjudicado"].sum()
        if total <= 0:
            continue
        cuotas = grupo.groupby(adjudicatario_col)["monto_adjudicado"].sum() / total * 100
        hhi = float((cuotas**2).sum())
        resultados.append(
            {
                "organismo": organismo,
                "hhi": round(hhi, 2),
                "n_proveedores": grupo[adjudicatario_col].nunique(),
                "proveedor_dominante": cuotas.idxmax(),
                "cuota_dominante_pct": round(cuotas.max(), 2),
                "alta_concentracion": hhi > 2500,
            }
        )
    return pd.DataFrame(resultados).sort_values("hhi", ascending=False)


# ---------------------------------------------------------------------------
# Low-balling index — desvío entre monto adjudicado y ejecutado
# ---------------------------------------------------------------------------

def low_balling_index(licitaciones: pd.DataFrame, adendas: pd.DataFrame) -> pd.DataFrame:
    """Ratio de adendas: (monto_ejecutado_final - monto_adjudicado) / monto_adjudicado.
    Valores altos sugieren oferta inicial artificialmente baja para ganar,
    con sobrecostos posteriores vía adendas."""
    total_adendas = (
        adendas.groupby("licitacion_id")
        .apply(lambda g: (g["monto_nuevo"] - g["monto_original"]).sum())
        .rename("ajuste_total_adendas")
    )
    df = licitaciones.merge(total_adendas, left_on="licitacion_id", right_index=True, how="left")
    df["ajuste_total_adendas"] = df["ajuste_total_adendas"].fillna(0.0)
    df["monto_final_estimado"] = df["monto_adjudicado"] + df["ajuste_total_adendas"]
    df["low_balling_ratio"] = np.where(
        df["monto_adjudicado"] > 0,
        (df["monto_final_estimado"] - df["monto_adjudicado"]) / df["monto_adjudicado"],
        np.nan,
    )
    return df[
        ["licitacion_id", "organismo", "monto_adjudicado", "monto_final_estimado", "low_balling_ratio"]
    ].sort_values("low_balling_ratio", ascending=False)


# ---------------------------------------------------------------------------
# ROI de campaña — aportantes vs. contrataciones posteriores
# ---------------------------------------------------------------------------

def roi_politico(
    aportes: pd.DataFrame,
    licitaciones: pd.DataFrame,
    ventana_dias_post_eleccion: int = 730,
) -> pd.DataFrame:
    """Cruza aportantes de campaña con contrataciones obtenidas dentro de
    la ventana temporal posterior a la elección. `aportes` requiere
    aportante(empresa), fecha, monto; `licitaciones` requiere proveedor,
    fecha_adjudicacion, monto_adjudicado."""
    aportes = aportes.copy()
    licitaciones = licitaciones.copy()
    aportes["fecha"] = pd.to_datetime(aportes["fecha"])
    licitaciones["fecha_adjudicacion"] = pd.to_datetime(licitaciones["fecha_adjudicacion"])

    resultados = []
    for empresa, grupo_aportes in aportes.groupby("aportante"):
        monto_aportado = grupo_aportes["monto"].sum()
        fecha_max_aporte = grupo_aportes["fecha"].max()
        ventana_fin = fecha_max_aporte + pd.Timedelta(days=ventana_dias_post_eleccion)

        contratos_posteriores = licitaciones[
            (licitaciones["proveedor"] == empresa)
            & (licitaciones["fecha_adjudicacion"] > fecha_max_aporte)
            & (licitaciones["fecha_adjudicacion"] <= ventana_fin)
        ]
        monto_adjudicado = contratos_posteriores["monto_adjudicado"].sum()
        roi = (monto_adjudicado / monto_aportado) if monto_aportado > 0 else np.nan

        resultados.append(
            {
                "empresa": empresa,
                "monto_aportado": monto_aportado,
                "n_contratos_posteriores": len(contratos_posteriores),
                "monto_adjudicado_posterior": monto_adjudicado,
                "roi_politico": round(roi, 2) if pd.notna(roi) else None,
            }
        )
    return pd.DataFrame(resultados).sort_values("roi_politico", ascending=False, na_position="last")
