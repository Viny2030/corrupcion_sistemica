"""Conector: MEACI (Auditoría de Integridad Corporativa / Compliance).

A diferencia de los demás conectores, MEACI no es una fuente pública con
API o buscador web: es el sensor interno que consolida auditorías de
integridad/compliance de contratistas (programas de integridad, Ley
27.401 en Argentina). No existiendo un portal público unificado, este
módulo NO simula auditorías: se limita a cargar exportaciones reales
(CSV/XLSX) que el equipo de auditoría interna o el propio organismo de
control (ej. Oficina Anticorrupción) entregue, y a normalizarlas al
esquema `auditoria_compliance`.

Si en el futuro el organismo publica una API, basta reemplazar
`cargar_export_csv` por un método `fetch()` real sin tocar el resto del
pipeline.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from ingestion.base import ConectorBase


class ConectorMEACICompliance(ConectorBase):
    fuente = "MEACI"

    def fetch(self, path_export: str | Path) -> pd.DataFrame:
        path_export = Path(path_export)
        if not path_export.exists():
            raise FileNotFoundError(
                f"No se encontró el export de auditorías MEACI en {path_export}. "
                "Este conector requiere un archivo real provisto por el organismo "
                "de control; no genera datos de compliance sintéticos."
            )
        return pd.read_csv(path_export) if path_export.suffix == ".csv" else pd.read_excel(path_export)

    def normalize(self, raw: pd.DataFrame) -> list[dict[str, Any]]:
        raw.columns = [str(c).strip().lower().replace(" ", "_") for c in raw.columns]
        registros = []
        for _, fila in raw.iterrows():
            registros.append(
                {
                    "empresa": fila.get("empresa") or fila.get("razon_social"),
                    "fecha": fila.get("fecha_auditoria") or fila.get("fecha"),
                    "tiene_programa_integridad": bool(fila.get("programa_integridad", False)),
                    "score_efectividad": fila.get("score_efectividad") or fila.get("score"),
                    "hallazgos": fila.get("hallazgos"),
                    "fuente": self.fuente,
                }
            )
        return registros
