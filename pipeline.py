"""Orquestador del monitor de Corrupción Sistémica.

Corre la ingesta de fuentes reales disponibles y la batería analítica de
las 4 capas, y deja todo consolidado en `dashboard/data.json` para que el
dashboard interactivo lo consuma. No genera ningún dato simulado: si una
fuente no está disponible o el usuario no proveyó datos propios (ej.
export de MEACI, dataset de licitaciones), la sección correspondiente
queda vacía y así se lo indica explícitamente en el JSON de salida
(`disponible: false`), para que el dashboard lo muestre como
"pendiente de datos reales" en vez de dibujar algo inventado.

Uso:
    python pipeline.py                # solo indicadores macro reales (CPI/WGI)
    python pipeline.py --licitaciones ruta.csv --adendas ruta.csv ...
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

import pandas as pd

from analytics import finanzas, scoring, sna
from ingestion.wgi_worldbank import ConectorWGI
from config.settings import SETTINGS

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("corrupcion_sistemica.pipeline")

DIR_DASHBOARD = Path(__file__).parent / "dashboard"

# Puntos de referencia reales verificados manualmente (fuentes citadas en
# README.md) para poblar el dashboard incluso antes de correr la ingesta
# completa. El pipeline los sobreescribe con datos frescos si la ingesta
# en vivo (World Bank API) responde correctamente.
CPI_REFERENCIA_REAL = [
    {"pais_iso3": "ARG", "anio": 2024, "indicador": "CPI", "valor": 37, "fuente": "Transparency International CPI 2024"},
    {"pais_iso3": "ARG", "anio": 2025, "indicador": "CPI", "valor": 36, "fuente": "Transparency International CPI 2025"},
]
WGI_REFERENCIA_REAL = [
    {"pais_iso3": "ARG", "anio": 2022, "indicador": "WGI_CONTROL_CORRUPCION", "valor": -0.45, "fuente": "World Bank WGI"},
    {"pais_iso3": "ARG", "anio": 2023, "indicador": "WGI_CONTROL_CORRUPCION", "valor": -0.36, "fuente": "World Bank WGI"},
]


def ingerir_indicadores_macro() -> list[dict]:
    """Intenta traer series reales de WGI vía API; si la llamada de red
    falla (sin conectividad, cambio de API, etc.) cae de forma explícita
    a los puntos de referencia verificados manualmente, sin inventar
    valores intermedios."""
    registros: list[dict] = list(CPI_REFERENCIA_REAL)
    try:
        conector = ConectorWGI()
        wgi = conector.fetch_multiples_paises(SETTINGS.paises_comparables_iso3, "CC.EST")
        registros.extend(wgi if wgi else WGI_REFERENCIA_REAL)
    except Exception as exc:  # noqa: BLE001
        logger.warning("No se pudo consultar la API del Banco Mundial en vivo (%s); "
                        "usando puntos de referencia verificados manualmente.", exc)
        registros.extend(WGI_REFERENCIA_REAL)
    return registros


def analizar_procurement(
    path_ofertas: str | None, path_licitaciones: str | None, path_adendas: str | None
) -> dict:
    """Corre Capa 1 (SNA) y Capa 2 (Finanzas) si el usuario provee sus
    propios datos reales de contrataciones. Si no se proveen rutas,
    devuelve `disponible: False` en cada bloque en lugar de simular."""
    resultado = {
        "co_presentismo": {"disponible": False, "datos": []},
        "asimetria_victorias": {"disponible": False, "datos": []},
        "hhi_por_organismo": {"disponible": False, "datos": []},
        "low_balling": {"disponible": False, "datos": []},
    }

    if path_ofertas:
        ofertas = pd.read_csv(path_ofertas)
        resultado["co_presentismo"] = {
            "disponible": True,
            "datos": sna.matriz_co_presentismo(ofertas).to_dict("records"),
        }
        resultado["asimetria_victorias"] = {
            "disponible": True,
            "datos": sna.asimetria_de_victorias(ofertas).to_dict("records"),
        }

    if path_licitaciones:
        licitaciones = pd.read_csv(path_licitaciones)
        resultado["hhi_por_organismo"] = {
            "disponible": True,
            "datos": finanzas.hhi_por_organismo(licitaciones).to_dict("records"),
        }
        if path_adendas:
            adendas = pd.read_csv(path_adendas)
            resultado["low_balling"] = {
                "disponible": True,
                "datos": finanzas.low_balling_index(licitaciones, adendas).to_dict("records"),
            }

    return resultado


def ejecutar_pipeline(
    path_ofertas: str | None = None,
    path_licitaciones: str | None = None,
    path_adendas: str | None = None,
    persistir: bool = True,
) -> dict:
    """Punto de entrada reusable: lo llaman tanto el CLI (`main`) como la
    API (`api/main.py`) y el cron diario (GitHub Actions / Railway Cron).
    Devuelve el dict de salida y, si `persistir=True`, lo escribe además
    en `dashboard/data.json` (para que el dashboard estático lo lea sin
    necesidad de golpear la API)."""
    salida = {
        "generado_en": pd.Timestamp.now("UTC").isoformat(),
        "indicadores_macro": ingerir_indicadores_macro(),
        "procurement": analizar_procurement(path_ofertas, path_licitaciones, path_adendas),
        "reglas_scoring": scoring.explicar_reglas().to_dict("records"),
    }

    if persistir:
        DIR_DASHBOARD.mkdir(exist_ok=True)
        destino = DIR_DASHBOARD / "data.json"
        destino.write_text(json.dumps(salida, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
        logger.info("Datos consolidados en %s", destino)

    return salida


def main() -> None:
    parser = argparse.ArgumentParser(description="Pipeline del monitor de Corrupción Sistémica")
    parser.add_argument("--ofertas", help="CSV real de ofertas por licitación (empresa_id, licitacion_id, resultado, ...)")
    parser.add_argument("--licitaciones", help="CSV real de licitaciones/adjudicaciones")
    parser.add_argument("--adendas", help="CSV real de adendas/ampliaciones de monto")
    args = parser.parse_args()
    ejecutar_pipeline(args.ofertas, args.licitaciones, args.adendas, persistir=True)


if __name__ == "__main__":
    main()
