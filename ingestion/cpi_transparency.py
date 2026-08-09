"""Conector real: Transparency International — Corruption Perceptions Index (CPI).

Transparency International no expone una API REST estable: publica cada año
un archivo Excel/CSV descargable desde https://www.transparency.org/en/cpi/ .
Este conector:
  1) intenta localizar automáticamente el link de descarga vigente en la
     página oficial (scraping liviano, sin inventar URLs fijas por año), y
  2) si falla (cambio de maquetación, bloqueo, etc.), permite cargar el
     archivo oficial ya descargado manualmente por el usuario con
     `load_local_file()`.

En ningún caso se generan valores de CPI sintéticos: si no hay archivo
disponible, se devuelve una lista vacía.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
from bs4 import BeautifulSoup

from config.settings import SETTINGS
from ingestion.base import ConectorBase


class ConectorCPI(ConectorBase):
    fuente = "TRANSPARENCY_INTERNATIONAL_CPI"

    def fetch(self) -> str | None:
        """Devuelve la URL del dataset CPI vigente encontrada en la página
        oficial, o None si no se pudo determinar automáticamente."""
        resp = self._get(SETTINGS.endpoints.cpi_landing)
        soup = BeautifulSoup(resp.text, "lxml")
        for link in soup.find_all("a", href=True):
            href = link["href"]
            if href.lower().endswith((".xlsx", ".xls", ".csv")):
                return href if href.startswith("http") else f"https://www.transparency.org{href}"
        return None

    def normalize(self, raw: str | None) -> list[dict[str, Any]]:
        if not raw:
            return []
        df = pd.read_excel(raw) if raw.lower().endswith((".xlsx", ".xls")) else pd.read_csv(raw)
        return self._normalize_dataframe(df)

    def load_local_file(self, path: str | Path) -> list[dict[str, Any]]:
        """Carga el archivo CPI oficial ya descargado manualmente por el
        usuario desde transparency.org. Es la vía recomendada para
        reproducibilidad (evita depender del scraping de la landing page)."""
        path = Path(path)
        df = pd.read_excel(path) if path.suffix.lower() in (".xlsx", ".xls") else pd.read_csv(path)
        return self._normalize_dataframe(df)

    @staticmethod
    def _normalize_dataframe(df: pd.DataFrame) -> list[dict[str, Any]]:
        """El archivo oficial de TI trae columnas tipo 'Country / Territory',
        'ISO3', 'CPI score <año>' repetidas por año. Se pivotea a formato
        largo (pais_iso3, anio, indicador='CPI', valor)."""
        df.columns = [str(c).strip() for c in df.columns]
        col_iso3 = next((c for c in df.columns if c.upper() in ("ISO3", "ISO CODE")), None)
        if col_iso3 is None:
            return []

        registros: list[dict[str, Any]] = []
        for col in df.columns:
            if "cpi score" in col.lower() or "cpi_score" in col.lower():
                anio = "".join(filter(str.isdigit, col))
                if not anio:
                    continue
                for _, fila in df[[col_iso3, col]].dropna().iterrows():
                    registros.append(
                        {
                            "pais_iso3": str(fila[col_iso3]).strip(),
                            "anio": int(anio),
                            "indicador": "CPI",
                            "valor": float(fila[col]),
                            "fuente": "TRANSPARENCY_INTERNATIONAL_CPI",
                        }
                    )
        return registros
