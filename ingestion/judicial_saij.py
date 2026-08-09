"""Conector real: SAIJ (Sistema Argentino de Información Jurídica) — Poder Judicial.

Fuente: http://www.saij.gob.ar/busqueda — buscador público de normativa y
jurisprudencia del Ministerio de Justicia. No hay API formal documentada;
se automatiza el buscador para extraer fallos reales relacionados con
causas de corrupción (texto completo, carátula, fuero, fecha), insumo de
`analytics/judicial_nlp.py` (sesgo de sanción, tasa de prescripción).
"""

from __future__ import annotations

from typing import Any

from bs4 import BeautifulSoup

from config.settings import SETTINGS
from ingestion.base import ConectorBase


class ConectorSAIJ(ConectorBase):
    fuente = "SAIJ_POJER_JUDICIAL"

    def fetch(self, texto_busqueda: str = "corrupción administrativa", pagina: int = 1) -> str:
        params = {"texto": texto_busqueda, "pagina": pagina}
        resp = self._get(SETTINGS.endpoints.saij_buscador, params=params)
        return resp.text

    def normalize(self, raw: str) -> list[dict[str, Any]]:
        soup = BeautifulSoup(raw, "lxml")
        registros: list[dict[str, Any]] = []
        for item in soup.select(".resultado-documento, .doc-item"):
            caratula = item.find(class_="caratula")
            fuero = item.find(class_="fuero")
            fecha = item.find(class_="fecha")
            texto = item.find(class_="texto-fallo")
            registros.append(
                {
                    "caratula": caratula.get_text(strip=True) if caratula else None,
                    "fuero": fuero.get_text(strip=True) if fuero else None,
                    "fecha_resolucion": fecha.get_text(strip=True) if fecha else None,
                    "texto_fallo": texto.get_text(" ", strip=True) if texto else None,
                    "fuente": self.fuente,
                }
            )
        return registros
