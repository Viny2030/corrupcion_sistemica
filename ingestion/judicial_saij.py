"""Conector real: SAIJ (Sistema Argentino de Información Jurídica) — Poder Judicial.

Fuente: http://www.saij.gob.ar/busqueda — buscador público de normativa y
jurisprudencia del Ministerio de Justicia.

VERIFICADO ESTA SESIÓN: pedir el HTML con un cliente HTTP simple devuelve
la página vacía. Este conector usa Playwright (`ingestion/_browser.py`)
para escribir la búsqueda real y leer los resultados ya renderizados.
No hay API formal documentada; se automatiza el buscador para extraer
fallos reales (texto completo, carátula, fuero, fecha), insumo de
`analytics/judicial_nlp.py`. Si la búsqueda no devuelve resultados
renderizados, se devuelve lista vacía (nunca se inventa jurisprudencia).
"""

from __future__ import annotations

import re
from typing import Any

from bs4 import BeautifulSoup

from config.settings import SETTINGS
from ingestion._browser import obtener_html_renderizado
from ingestion.base import ConectorBase

PATRON_FECHA = re.compile(r"\b\d{1,2}/\d{1,2}/\d{4}\b")


class ConectorSAIJ(ConectorBase):
    fuente = "SAIJ_PODER_JUDICIAL"

    def fetch(self, texto_busqueda: str = "corrupción administrativa", timeout_ms: int = 25000) -> str:
        def _buscar(pagina) -> None:  # noqa: ANN001
            campo = pagina.get_by_role("searchbox")
            if campo.count() == 0:
                campo = pagina.get_by_placeholder(re.compile("buscar", re.I))
            campo.first.fill(texto_busqueda)
            campo.first.press("Enter")
            pagina.wait_for_load_state("networkidle", timeout=timeout_ms)

        return obtener_html_renderizado(
            SETTINGS.endpoints.saij_buscador,
            acciones=_buscar,
            timeout_ms=timeout_ms,
        )

    def normalize(self, raw: str) -> list[dict[str, Any]]:
        soup = BeautifulSoup(raw, "lxml")
        registros = self._extraer_con_selectores_conocidos(soup)
        if not registros:
            registros = self._extraer_por_heuristica_generica(soup)
        return registros

    def _extraer_con_selectores_conocidos(self, soup: BeautifulSoup) -> list[dict[str, Any]]:
        registros = []
        for item in soup.select(".resultado-documento, .doc-item"):
            caratula = item.find(class_=re.compile("caratula", re.I))
            fuero = item.find(class_=re.compile("fuero", re.I))
            fecha = item.find(class_=re.compile("fecha", re.I))
            texto = item.find(class_=re.compile("texto-fallo|sumario", re.I))
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

    def _extraer_por_heuristica_generica(self, soup: BeautifulSoup) -> list[dict[str, Any]]:
        """Fallback: cada resultado suele ser un bloque (article/li/div)
        con un encabezado (carátula) y una fecha DD/MM/AAAA cerca."""
        registros = []
        for encabezado in soup.find_all(["h2", "h3", "h4"]):
            bloque = encabezado.find_parent(["article", "li", "div"]) or encabezado
            texto_bloque = bloque.get_text(" ", strip=True)
            match_fecha = PATRON_FECHA.search(texto_bloque)
            if len(texto_bloque) < 15:
                continue
            registros.append(
                {
                    "caratula": encabezado.get_text(strip=True),
                    "fuero": None,
                    "fecha_resolucion": match_fecha.group(0) if match_fecha else None,
                    "texto_fallo": texto_bloque,
                    "fuente": self.fuente,
                }
            )
        return registros
