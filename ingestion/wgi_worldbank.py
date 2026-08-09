"""Conector real: World Bank — Worldwide Governance Indicators (WGI).

API pública, sin API key. Documentación: https://datahelpdesk.worldbank.org/

Indicadores relevantes:
    CC.EST  -> Control of Corruption: Estimate
    RL.EST  -> Rule of Law: Estimate
    GE.EST  -> Government Effectiveness: Estimate
    RQ.EST  -> Regulatory Quality: Estimate
"""

from __future__ import annotations

from typing import Any

from config.settings import SETTINGS
from ingestion.base import ConectorBase

INDICADORES_WGI = {
    "CC.EST": "WGI_CONTROL_CORRUPCION",
    "RL.EST": "WGI_RULE_OF_LAW",
    "GE.EST": "WGI_GOBIERNO_EFECTIVO",
    "RQ.EST": "WGI_CALIDAD_REGULATORIA",
}


class ConectorWGI(ConectorBase):
    fuente = "WORLD_BANK_WGI"

    def fetch(
        self,
        pais_iso3: str = "ARG",
        indicador_codigo: str = "CC.EST",
        anio_desde: int = 2000,
        anio_hasta: int = 2024,
    ) -> list[dict]:
        url = SETTINGS.endpoints.wgi_api_base.format(
            country=pais_iso3, indicator=indicador_codigo
        )
        params = {
            "format": "json",
            "date": f"{anio_desde}:{anio_hasta}",
            "per_page": 500,
            # Los indicadores WGI (CC.EST, RL.EST, GE.EST, RQ.EST) viven en el
            # dataset "Worldwide Governance Indicators" (source=3) del Banco
            # Mundial, no en el WDI por defecto (source=2). Sin este parámetro
            # la API responde "indicator not found".
            "source": 3,
        }
        resp = self._get(url, params=params)
        payload = resp.json()
        # La API del Banco Mundial devuelve [metadata, data]
        if not isinstance(payload, list) or len(payload) < 2 or payload[1] is None:
            return []
        return payload[1]

    def normalize(self, raw: list[dict]) -> list[dict[str, Any]]:
        registros = []
        for item in raw:
            if item.get("value") is None:
                continue
            registros.append(
                {
                    "pais_iso3": item["countryiso3code"],
                    "anio": int(item["date"]),
                    "indicador": INDICADORES_WGI.get(
                        item["indicator"]["id"], item["indicator"]["id"]
                    ),
                    "valor": float(item["value"]),
                    "fuente": self.fuente,
                }
            )
        return registros

    def fetch_multiples_paises(
        self, paises_iso3: tuple[str, ...], indicador_codigo: str = "CC.EST"
    ) -> list[dict]:
        """Conveniencia: trae el mismo indicador para varios países reales
        (ej. comparables regionales) en una sola pasada."""
        resultados: list[dict] = []
        for pais in paises_iso3:
            raw = self.fetch(pais_iso3=pais, indicador_codigo=indicador_codigo)
            resultados.extend(self.normalize(raw))
        return resultados
