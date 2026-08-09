"""Conector real: Cámara de Diputados de la Nación (HCDN) — Votaciones.

Fuentes oficiales reales:
    - https://datos.hcdn.gob.ar          (portal de datos abiertos)
    - https://votaciones.hcdn.gob.ar     (buscador de actas de votación,
      publica registros en CSV/Excel reutilizables por Ley 27.275)

VERIFICADO ESTA SESIÓN: votaciones.hcdn.gob.ar es una SPA — pedir el HTML
con un cliente HTTP simple devuelve la página vacía (el contenido se
arma en el navegador). Este conector usa Playwright (`ingestion/_browser.py`)
para renderizar la página real y buscar los enlaces de descarga (CSV/XLSX)
que HCDN publica por cada acta. Si no aparecen enlaces de descarga directos,
cae a un parser genérico de tabla sobre el resultado renderizado.

No se genera ningún voto sintético: si una sesión no tiene archivo
publicado ni tabla de resultados, simplemente no se incorpora.
"""

from __future__ import annotations

import re
from typing import Any

import pandas as pd
from bs4 import BeautifulSoup

from config.settings import SETTINGS
from ingestion._browser import obtener_html_renderizado
from ingestion.base import ConectorBase


class ConectorHCDNVotaciones(ConectorBase):
    fuente = "HCDN_VOTACIONES"

    def fetch(self, anio: int, timeout_ms: int = 25000) -> str:
        """Renderiza el buscador real de HCDN filtrado por año y devuelve
        el HTML del DOM resultante (con los links de descarga o la tabla
        de resultados, según lo que la SPA haya montado)."""

        def _filtrar_por_anio(pagina) -> None:  # noqa: ANN001
            try:
                selector_anio = pagina.get_by_label(re.compile("a[ñn]o", re.I))
                if selector_anio.count():
                    selector_anio.first.select_option(label=str(anio))
                    pagina.wait_for_load_state("networkidle", timeout=timeout_ms)
            except Exception:  # noqa: BLE001 — el filtro es best-effort
                pass

        return obtener_html_renderizado(
            f"{SETTINGS.endpoints.hcdn_votaciones}/?anio={anio}",
            acciones=_filtrar_por_anio,
            timeout_ms=timeout_ms,
        )

    def normalize(self, raw: str) -> list[dict[str, Any]]:
        soup = BeautifulSoup(raw, "lxml")
        links_descarga = self._extraer_links_descarga(soup)
        if links_descarga:
            return self._normalizar_desde_archivos(links_descarga)
        return self._normalizar_desde_tabla_renderizada(soup)

    @staticmethod
    def _extraer_links_descarga(soup: BeautifulSoup) -> list[str]:
        links = []
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if href.lower().endswith((".csv", ".xlsx", ".xls")):
                links.append(href if href.startswith("http") else f"{SETTINGS.endpoints.hcdn_votaciones}{href}")
        return links

    def _normalizar_desde_archivos(self, urls: list[str]) -> list[dict[str, Any]]:
        registros: list[dict[str, Any]] = []
        for url in urls:
            try:
                df = pd.read_csv(url) if url.lower().endswith("csv") else pd.read_excel(url)
            except Exception:  # noqa: BLE001 — fuente externa puede fallar/cambiar formato
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

    def _normalizar_desde_tabla_renderizada(self, soup: BeautifulSoup) -> list[dict[str, Any]]:
        """Fallback genérico: toma la primera tabla cuyo encabezado
        contenga columnas reconocibles (diputado/voto/bloque)."""
        registros: list[dict[str, Any]] = []
        for tabla in soup.find_all("table"):
            encabezados = [th.get_text(strip=True).lower() for th in tabla.find_all("th")]
            if not any(k in " ".join(encabezados) for k in ("diputado", "legislador", "voto")):
                continue
            indices = {nombre: i for i, nombre in enumerate(encabezados)}
            for tr in tabla.find_all("tr")[1:]:
                celdas = [td.get_text(strip=True) for td in tr.find_all("td")]
                if not celdas:
                    continue

                def val(clave_posibles: list[str]) -> str | None:
                    for clave in clave_posibles:
                        idx = indices.get(clave)
                        if idx is not None and idx < len(celdas):
                            return celdas[idx]
                    return None

                registros.append(
                    {
                        "camara": "DIPUTADOS",
                        "expediente": val(["expediente"]),
                        "titulo": val(["titulo", "asunto"]),
                        "fecha": val(["fecha"]),
                        "legislador": val(["diputado", "legislador"]),
                        "voto": val(["voto"]),
                        "bloque": val(["bloque"]),
                        "fuente": self.fuente,
                    }
                )
            break  # solo la primera tabla reconocida
        return registros
