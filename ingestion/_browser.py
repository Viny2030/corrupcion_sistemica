"""Helper compartido para conectores sobre sitios renderizados por
JavaScript (SPA).

Verificación real (esta sesión): al pedir el HTML crudo de
boletinoficial.gob.ar, votaciones.hcdn.gob.ar, senado.gob.ar y saij.gob.ar
con un cliente HTTP simple, las cuatro respuestas vinieron vacías o solo
con el "shell" de la aplicación (loaders, `<div id="app">` vacío, etc.):
son SPAs que arman el contenido en el navegador, no server-rendered HTML.
Por eso estos conectores no pueden depender de `requests` + BeautifulSoup
para el contenido dinámico: necesitan un navegador real (headless) que
ejecute el JS antes de parsear.

Este módulo centraliza esa lógica con Playwright. Si Playwright no está
instalado, lo dice explícitamente en el error en vez de fallar con un
traceback confuso.
"""

from __future__ import annotations

import logging
from typing import Callable, Optional

logger = logging.getLogger("mapa_transparencia.ingestion.browser")


def obtener_html_renderizado(
    url: str,
    esperar_selector: Optional[str] = None,
    acciones: Optional[Callable[["Page"], None]] = None,  # type: ignore[name-defined]
    timeout_ms: int = 20000,
    espera_extra_ms: int = 1500,
) -> str:
    """Abre `url` en Chromium headless, ejecuta el JS de la página, espera
    a que aparezca `esperar_selector` (si se indica) y devuelve el HTML del
    DOM ya renderizado. `acciones` permite inyectar pasos reales (llenar un
    formulario, hacer clic en "Buscar") antes de leer el resultado.

    Requiere: `pip install playwright && playwright install chromium`.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "Este conector requiere Playwright para renderizar sitios SPA. "
            "Instalar con: pip install playwright && playwright install chromium"
        ) from exc

    with sync_playwright() as pw:
        navegador = pw.chromium.launch(headless=True)
        pagina = navegador.new_page()
        try:
            pagina.goto(url, timeout=timeout_ms, wait_until="networkidle")
            if acciones:
                acciones(pagina)
            if esperar_selector:
                pagina.wait_for_selector(esperar_selector, timeout=timeout_ms)
            else:
                pagina.wait_for_timeout(espera_extra_ms)
            return pagina.content()
        finally:
            navegador.close()
