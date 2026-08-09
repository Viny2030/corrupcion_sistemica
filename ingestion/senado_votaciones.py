"""Conector real: Senado de la Nación Argentina — Votaciones.

Fuente: https://www.senado.gob.ar/parlamentario/parlamentaria/votaciones
El Senado no ofrece API pública formal; este conector navega el listado
público de votaciones y descarga las actas reales publicadas en PDF/CSV
cuando están disponibles. Igual que en el conector de HCDN, no se fabrica
ningún voto: solo se incorporan actas efectivamente publicadas.
"""

from __future__ import annotations

from typing import Any

from bs4 import BeautifulSoup

from config.settings import SETTINGS
from ingestion.base import ConectorBase


class ConectorSenadoVotaciones(ConectorBase):
    fuente = "SENADO_VOTACIONES"

    def fetch(self, anio: int) -> list[dict]:
        resp = self._get(SETTINGS.endpoints.senado_datos_abiertos, params={"anio": anio})
        soup = BeautifulSoup(resp.text, "lxml")
        filas = []
        tabla = soup.find("table")
        if tabla is None:
            return filas
        for tr in tabla.find_all("tr")[1:]:
            celdas = [td.get_text(strip=True) for td in tr.find_all("td")]
            if celdas:
                filas.append(celdas)
        return filas

    def normalize(self, raw: list[list[str]]) -> list[dict[str, Any]]:
        registros = []
        for celdas in raw:
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
