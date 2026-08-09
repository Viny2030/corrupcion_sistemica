"""Utilidad de calibración: vuelca el HTML REAL ya renderizado de un sitio
SPA (BORA, HCDN, Senado, SAIJ) a un archivo, para que puedas inspeccionarlo
y ajustar los selectores en `ingestion/*.py` si la maquetación cambió o si
las clases CSS que usé como primer intento no coinciden.

No pude ejecutar esto yo mismo en la sesión donde escribí los conectores
(sin navegador ni sandbox disponibles), así que los selectores "conocidos"
en bora_boletin.py / judicial_saij.py son un primer intento razonable, no
una verificación contra el DOM real. Este script cierra esa brecha.

Uso:
    playwright install chromium   # una sola vez
    python scripts/inspeccionar_selectores.py bora
    python scripts/inspeccionar_selectores.py hcdn --anio 2025
    python scripts/inspeccionar_selectores.py senado --anio 2025
    python scripts/inspeccionar_selectores.py saij --texto "corrupción"

El HTML renderizado queda en scripts/_dump_<sitio>.html
"""

from __future__ import annotations

import argparse
from pathlib import Path

from config.settings import SETTINGS
from ingestion._browser import obtener_html_renderizado

DIR_SALIDA = Path(__file__).parent


def main() -> None:
    parser = argparse.ArgumentParser(description="Vuelca el HTML renderizado real de un sitio SPA")
    parser.add_argument("sitio", choices=["bora", "hcdn", "senado", "saij"])
    parser.add_argument("--anio", type=int, default=2025)
    parser.add_argument("--texto", default="corrupción administrativa")
    args = parser.parse_args()

    urls = {
        "bora": SETTINGS.endpoints.bora_buscador,
        "hcdn": f"{SETTINGS.endpoints.hcdn_votaciones}/?anio={args.anio}",
        "senado": f"{SETTINGS.endpoints.senado_datos_abiertos}?anio={args.anio}",
        "saij": SETTINGS.endpoints.saij_buscador,
    }

    html = obtener_html_renderizado(urls[args.sitio], timeout_ms=30000)
    destino = DIR_SALIDA / f"_dump_{args.sitio}.html"
    destino.write_text(html, encoding="utf-8")
    print(f"HTML renderizado guardado en {destino}")
    print("Abrilo en el navegador o inspeccionalo para actualizar los selectores en ingestion/.")


if __name__ == "__main__":
    main()
