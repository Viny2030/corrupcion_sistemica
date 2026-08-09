"""Conector real: Cámara de Diputados de la Nación (HCDN) — Votaciones.

Fuentes oficiales reales:
    - https://datos.hcdn.gob.ar          (portal de datos abiertos)
    - https://votaciones.hcdn.gob.ar     (buscador de actas de votación,
      publica registros en CSV/Excel reutilizables por Ley 27.275)

HCDN no publica una API REST formal y estable, por lo que este conector
navega el buscador público y descarga los archivos de actas reales que
el propio sitio expone (no hay generación de votos sintéticos: si una
sesión no tiene archivo publicado, simplemente no se incorpora).

NOTA DE MANTENIMIENTO: los selectores de scraping (`_extraer_links_descarga`)
dependen de la maquetación vigente del sitio y pueden requerir ajuste si
HCDN cambia su HTML. Se aísla esa lógica en un solo método para facilitar
el mantenimiento.
"""

from __future__ import annotations

from typing import Any

import pandas as pd
from bs4 import BeautifulSoup

from config.settings import SETTINGS
from ingestion.base import ConectorBase


class ConectorHCDNVotaciones(ConectorBase):
    fuente = "HCDN_VOTACIONES"

    def fetch(self, anio: int) -> list[str]:
        """Busca actas de votación reales del año dado y devuelve las URLs
        de descarga (CSV/XLSX) publicadas por HCDN."""
        resp = self._get(SETTINGS.endpoints.hcdn_votaciones, params={"anio": anio})
        return self._extraer_links_descarga(resp.text)

    @staticmethod
    def _extraer_links_descarga(html: str) -> list[str]:
        soup = BeautifulSoup(html, "lxml")
        links = []
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if href.lower().endswith((".csv", ".xlsx", ".xls")):
                links.append(href if href.startswith("http") else f"{SETTINGS.endpoints.hcdn_votaciones}{href}")
        return links

    def normalize(self, raw: list[str]) -> list[dict[str, Any]]:
        registros: list[dict[str, Any]] = []
        for url in raw:
            try:
                df = pd.read_csv(url) if url.lower().endswith("csv") else pd.read_excel(url)
            except Exception:  # noqa: BLE001
                continue
            df.columns = [str(c).strip().lower().replace(" ", "_") for c in df.columns]
            for _, fila in df.iterrows():
                registros.append(
                    {
                        "camara": "DIPUTADOS",
                        "expediente": fila.get("expediente") or fila.get("id_votacion"),
                        "titulo": fila.get("titulo") or fila.get("asunto"),
                        "fecha": fila.get("fecha"),
                        "legislador": fila.get("diputado") or fila.get("legislador"),
                        "voto": fila.get("voto"),
                        "bloque": fila.get("bloque"),
                        "fuente": self.fuente,
                    }
                )
        return registros
