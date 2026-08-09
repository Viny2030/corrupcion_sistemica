"""Conector real: Boletín Oficial de la República Argentina (BORA).

BORA no tiene API pública; expone un buscador web
(https://www.boletinoficial.gob.ar/busquedaAvanzada/primera). Este conector
automatiza búsquedas reales por texto/fecha/organismo y extrae los avisos
publicados (pliegos, adjudicaciones, decretos) que alimentan "Monitor
Contratos". Al no existir API, la solidez del scraping depende de la
maquetación vigente del sitio; se documenta explícitamente qué selectores
usar y se recomienda validar periódicamente contra el HTML real.
"""

from __future__ import annotations

from typing import Any

from bs4 import BeautifulSoup

from config.settings import SETTINGS
from ingestion.base import ConectorBase


class ConectorBORA(ConectorBase):
    fuente = "BORA"

    def fetch(self, texto_busqueda: str, fecha_desde: str, fecha_hasta: str) -> str:
        """Ejecuta una búsqueda real en BORA y devuelve el HTML de resultados.
        `fecha_desde`/`fecha_hasta` en formato DD/MM/AAAA, según el buscador
        oficial."""
        params = {
            "aviso.textoAviso": texto_busqueda,
            "aviso.fechaDesde": fecha_desde,
            "aviso.fechaHasta": fecha_hasta,
        }
        resp = self._get(SETTINGS.endpoints.bora_buscador, params=params)
        return resp.text

    def normalize(self, raw: str) -> list[dict[str, Any]]:
        soup = BeautifulSoup(raw, "lxml")
        registros: list[dict[str, Any]] = []
        for item in soup.select(".resultado-aviso, .aviso-item"):
            titulo = item.find(class_="titulo")
            fecha = item.find(class_="fecha")
            organismo = item.find(class_="organismo")
            enlace = item.find("a", href=True)
            registros.append(
                {
                    "titulo": titulo.get_text(strip=True) if titulo else None,
                    "fecha": fecha.get_text(strip=True) if fecha else None,
                    "organismo": organismo.get_text(strip=True) if organismo else None,
                    "url": enlace["href"] if enlace else None,
                    "fuente": self.fuente,
                }
            )
        return registros
