"""Conector real: Boletín Oficial de la República Argentina (BORA).

VERIFICADO ESTA SESIÓN: https://www.boletinoficial.gob.ar/busquedaAvanzada/primera
es una SPA (Angular) — el HTML servido por el backend trae únicamente el
formulario y placeholders "Loading..." para los combos; los resultados se
renderizan en el navegador tras ejecutar JS. No hay API pública documentada,
así que este conector usa un navegador real headless (Playwright, ver
`ingestion/_browser.py`) para completar el formulario real ("Palabra/s
clave" + botón "Buscar") y leer el DOM ya renderizado.

Como no pude verificar contra el sitio en vivo en esta sesión (sin acceso
a navegador), la extracción usa selectores de texto/rol (más estables que
clases CSS) y cae a una heurística genérica basada en patrones de fecha y
enlaces si la estructura específica no matchea. Calibrar con
`scripts/inspeccionar_selectores.py` antes de producción.
"""

from __future__ import annotations

import re
from typing import Any

from bs4 import BeautifulSoup

from config.settings import SETTINGS
from ingestion._browser import obtener_html_renderizado
from ingestion.base import ConectorBase

PATRON_FECHA = re.compile(r"\b\d{1,2}/\d{1,2}/\d{4}\b")


class ConectorBORA(ConectorBase):
    fuente = "BORA"

    def fetch(self, texto_busqueda: str, timeout_ms: int = 25000) -> str:
        """Completa el buscador real de BORA con `texto_busqueda` y
        devuelve el HTML renderizado de los resultados."""

        def _buscar(pagina) -> None:  # noqa: ANN001 — tipo real es playwright.sync_api.Page
            campo = pagina.get_by_placeholder(re.compile("palabra", re.I))
            if campo.count() == 0:
                campo = pagina.get_by_label(re.compile("palabra", re.I))
            campo.first.fill(texto_busqueda)

            boton = pagina.get_by_role("button", name=re.compile("buscar", re.I))
            boton.first.click()
            pagina.wait_for_load_state("networkidle", timeout=timeout_ms)

        return obtener_html_renderizado(
            SETTINGS.endpoints.bora_buscador,
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
        """Intento con clases probables de la maquetación actual. Ajustar
        aquí primero si `scripts/inspeccionar_selectores.py` revela otras."""
        registros = []
        for item in soup.select(".resultado-aviso, .aviso-item, .card-aviso"):
            titulo = item.find(class_=re.compile("titulo|denominacion", re.I))
            fecha = item.find(class_=re.compile("fecha", re.I))
            organismo = item.find(class_=re.compile("organismo|rubro", re.I))
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

    def _extraer_por_heuristica_generica(self, soup: BeautifulSoup) -> list[dict[str, Any]]:
        """Fallback sin depender de clases: busca enlaces a avisos/detalle
        y toma como título el texto del propio link, y como fecha la
        primera fecha DD/MM/AAAA encontrada en su bloque contenedor."""
        registros = []
        for enlace in soup.find_all("a", href=True):
            href = enlace["href"]
            if not re.search(r"/(detalleAviso|aviso|detalle)/", href, re.I):
                continue
            contenedor = enlace.find_parent(["li", "div", "article", "tr"]) or enlace
            texto_contenedor = contenedor.get_text(" ", strip=True)
            match_fecha = PATRON_FECHA.search(texto_contenedor)
            registros.append(
                {
                    "titulo": enlace.get_text(strip=True) or None,
                    "fecha": match_fecha.group(0) if match_fecha else None,
                    "organismo": None,
                    "url": href,
                    "fuente": self.fuente,
                }
            )
        return registros
