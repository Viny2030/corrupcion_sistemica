"""Scoring de riesgo sistémico y Explicabilidad Algorítmica (XAI).

Combina los indicadores de las 4 capas en un score 0-100 por licitación/
empresa, con un desglose explícito de qué factores reales activaron cada
punto ("Audit Card"), tal como pide la arquitectura:
    "+30% por HHI elevado, +25% por adendas repetidas, +20% por cobro
    veloz en TGN".

Los pesos son parámetros configurables y transparentes (no una caja
negra): cualquier auditor puede ver exactamente qué regla sumó qué
puntaje, y sobre qué dato real se basó.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd


@dataclass(frozen=True)
class ReglaScoring:
    nombre: str
    descripcion: str
    peso_maximo: float
    condicion: "callable"  # fila (pd.Series) -> bool
    intensidad: "callable" = field(default=lambda fila: 1.0)  # fila -> factor 0..1


REGLAS: list[ReglaScoring] = [
    ReglaScoring(
        nombre="HHI_ELEVADO",
        descripcion="Alta concentración presupuestaria en el organismo (HHI > 2500)",
        peso_maximo=30.0,
        condicion=lambda f: bool(f.get("alta_concentracion", False)),
    ),
    ReglaScoring(
        nombre="ADENDAS_REPETIDAS",
        descripcion="Low-balling ratio alto: sobrecosto significativo vía adendas",
        peso_maximo=25.0,
        condicion=lambda f: (f.get("low_balling_ratio") or 0) > 0.15,
        intensidad=lambda f: min((f.get("low_balling_ratio") or 0) / 0.5, 1.0),
    ),
    ReglaScoring(
        nombre="COBRO_VELOZ_TGN",
        descripcion="Priorización de pago frente al promedio del organismo",
        peso_maximo=20.0,
        condicion=lambda f: bool(f.get("priorizacion_detectada", False)),
        intensidad=lambda f: min((f.get("dias_ahorrados") or 0) / 30, 1.0),
    ),
    ReglaScoring(
        nombre="ALTERNANCIA_SOSPECHOSA",
        descripcion="Alternancia de victorias con co-presentismo alto (posible cobertura)",
        peso_maximo=15.0,
        condicion=lambda f: (f.get("indice_alternancia") or 0) > 0.7,
        intensidad=lambda f: f.get("indice_alternancia") or 0,
    ),
    ReglaScoring(
        nombre="COMPLIANCE_DE_PAPEL",
        descripcion="Programa de integridad declarado sin efectividad real verificada",
        peso_maximo=10.0,
        condicion=lambda f: bool(f.get("compliance_de_papel", False)),
    ),
]


def calcular_score(fila: pd.Series, reglas: list[ReglaScoring] = REGLAS) -> dict:
    """Devuelve {"score": float, "desglose": {regla: puntos, ...}}."""
    desglose = {}
    for regla in reglas:
        if regla.condicion(fila):
            puntos = round(regla.peso_maximo * regla.intensidad(fila), 2)
            desglose[regla.nombre] = puntos
    score_total = round(min(sum(desglose.values()), 100.0), 2)
    return {"score": score_total, "desglose": desglose}


def generar_audit_cards(tabla_indicadores: pd.DataFrame, reglas: list[ReglaScoring] = REGLAS) -> pd.DataFrame:
    """Aplica `calcular_score` fila a fila sobre una tabla ya cruzada con
    todos los indicadores de las 4 capas (una fila por licitación/empresa)
    y devuelve el score + audit card en formato tabular, listo para
    persistir en `score_riesgo.desglose` (JSONB)."""
    resultados = tabla_indicadores.apply(lambda fila: calcular_score(fila, reglas), axis=1)
    tabla_indicadores = tabla_indicadores.copy()
    tabla_indicadores["score_riesgo"] = resultados.apply(lambda r: r["score"])
    tabla_indicadores["audit_card"] = resultados.apply(lambda r: r["desglose"])
    return tabla_indicadores.sort_values("score_riesgo", ascending=False)


def explicar_reglas() -> pd.DataFrame:
    """Tabla de referencia de las reglas vigentes, para mostrar en el
    dashboard (transparencia del propio modelo de scoring)."""
    return pd.DataFrame(
        [
            {"regla": r.nombre, "descripcion": r.descripcion, "peso_maximo": r.peso_maximo}
            for r in REGLAS
        ]
    )
