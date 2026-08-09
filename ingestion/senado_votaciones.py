"""Conector real: Senado de la Nación Argentina — Votaciones.

Fuente: https://www.senado.gob.ar/parlamentario/parlamentaria/votaciones

VERIFICADO ESTA SESIÓN: pedir el HTML con un cliente HTTP simple devuelve
la página vacía (contenido armado por JS en el navegador). Este conector
usa Playwright (`ingestion/_browser.py`) para renderizar la página real y
parsea genéricamente la primera tabla de resultados. El Senado no ofrece
API pública formal; no se fabrica ningún voto — si no hay tabla renderizada,
se devuelve una lista vacía.
"""

from __future__ import annotations

from typing import Any

from bs4 import BeautifulSoup

from config.settings import SETTINGS
from ingestion._browser import obtener_html_renderizado
from ingestion.base import ConectorBase


class ConectorSenadoVotaciones(ConectorBase):
    fuente = "SENADO_VOTACIONES"

    def fetch(self, anio: int, timeout_ms: int = 25000) -> str:
        return obtener_html_renderizado(
            f"{SETTINGS.endpoints.senado_datos_abiertos}?anio={anio}",
            esperar_selector="table",
            timeout_ms=timeout_ms,
        )

    def normalize(self, raw: str) -> list[dict[str, Any]]:
        soup = BeautifulSoup(raw, "lxml")
        tabla = soup.find("table")
        if tabla is None:
            return []

        filas = []
        for tr in tabla.find_all("tr")[1:]:
            celdas = [td.get_text(strip=True) for td in tr.find_all("td")]
            if celdas:
                filas.append(celdas)

        registros = []
        for celdas in filas:
            if len(celdas) < 3:
                continue
            registros.append(
                {
                    "camara": "SENADORES",
                    "fecha": celdas[0],
                    "expediente": celdas[1],
                    "titulo": celdas[2] if len(celdas) > 2 else None,
                    "resultado": celdas[3] if len(celdas) > 3 else None,
                    "fuente": self.fuente,
                }
            )
        return registros
