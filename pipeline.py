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
from services import concentration_service, network_service, pattern_service, risk_service

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


def _persistir_procurement_en_postgres(
    licitaciones: pd.DataFrame, aristas: pd.DataFrame, tabla_ircs: pd.DataFrame
) -> None:
    """Persiste entidades/licitaciones/aristas/scores en Postgres real
    (`database/`) si hay conexión disponible (ver
    `database.connection.verificar_conexion()`). Si no la hay, o si algo
    falla durante la persistencia, se loguea una advertencia y el
    pipeline sigue solo con `dashboard/data.json` — nunca se cae por
    esto, misma filosofía que `ingerir_indicadores_macro()` con la API
    del Banco Mundial. Import perezoso de `database` para no requerir
    SQLAlchemy/psycopg2 en el path de quien solo usa CSV -> JSON."""
    from database.connection import sesion, verificar_conexion
    from database import repositories as db_repo

    if not verificar_conexion():
        logger.info("Postgres no disponible; se sigue solo con dashboard/data.json.")
        return
    try:
        with sesion() as session:
            entidades_map = db_repo.upsert_entidades_de_licitaciones(session, licitaciones)
            licitaciones_map = db_repo.persistir_licitaciones(session, licitaciones, entidades_map)
            n_aristas = db_repo.persistir_grafo_aristas(session, aristas, entidades_map)
            n_scores = db_repo.persistir_scores_riesgo(session, tabla_ircs, licitaciones_map)
        logger.info(
            "Corrida persistida en Postgres: %s licitaciones, %s aristas, %s scores.",
            len(licitaciones_map), n_aristas, n_scores,
        )
    except Exception as exc:  # noqa: BLE001 — no debe tumbar el pipeline
        logger.warning("No se pudo persistir en Postgres (%s); se sigue solo con dashboard/data.json.", exc)


def _persistir_indicadores_macro_en_postgres(indicadores_macro: list[dict]) -> None:
    """Igual filosofía que `_persistir_procurement_en_postgres`, pero
    para los indicadores macro (no depende de que haya licitaciones)."""
    from database.connection import sesion, verificar_conexion
    from database import repositories as db_repo

    if not verificar_conexion():
        return
    try:
        with sesion() as session:
            db_repo.persistir_indicadores_macro(session, indicadores_macro)
        logger.info("Indicadores macro persistidos en Postgres.")
    except Exception as exc:  # noqa: BLE001
        logger.warning("No se pudieron persistir los indicadores macro en Postgres (%s).", exc)


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
    path_ofertas: str | None,
    path_licitaciones: str | None,
    path_adendas: str | None,
    path_entidades: str | None = None,
    indicadores_macro: list[dict] | None = None,
) -> dict:
    """Corre Capa 1 (SNA) y Capa 2 (Finanzas), más los motores de
    concentración/redes/patrones/IRCS (`services/`), si el usuario provee
    sus propios datos reales de contrataciones. Si no se proveen rutas,
    devuelve `disponible: False` en cada bloque en lugar de simular.

    `path_entidades` es opcional y solo se usa para REGLA-004/REGLA-005
    del motor de patrones (mismo domicilio / mismo representante); sin
    él, esas dos reglas simplemente no encuentran evidencia."""
    resultado = {
        "co_presentismo": {"disponible": False, "datos": []},
        "asimetria_victorias": {"disponible": False, "datos": []},
        "hhi_por_organismo": {"disponible": False, "datos": []},
        "low_balling": {"disponible": False, "datos": []},
        "concentracion_top3": {"disponible": False, "datos": []},
        "concentracion_top5": {"disponible": False, "datos": []},
        "redes": {"disponible": False, "datos": []},
        "patrones": {"disponible": False, "datos": []},
        "anomalias": {"disponible": False, "datos": []},
        "riesgo_ircs": {"disponible": False, "datos": []},
    }

    ofertas = pd.read_csv(path_ofertas) if path_ofertas else None
    licitaciones = pd.read_csv(path_licitaciones) if path_licitaciones else None
    adendas = pd.read_csv(path_adendas) if path_adendas else None
    entidades = pd.read_csv(path_entidades) if path_entidades else None

    if ofertas is not None:
        resultado["co_presentismo"] = {
            "disponible": True,
            "datos": sna.matriz_co_presentismo(ofertas).to_dict("records"),
        }
        resultado["asimetria_victorias"] = {
            "disponible": True,
            "datos": sna.asimetria_de_victorias(ofertas).to_dict("records"),
        }

    if licitaciones is not None:
        tabla_hhi = finanzas.hhi_por_organismo(licitaciones)
        resultado["hhi_por_organismo"] = {"disponible": True, "datos": tabla_hhi.to_dict("records")}
        resultado["concentracion_top3"] = {
            "disponible": True,
            "datos": concentration_service.concentracion_top_n(licitaciones, 3).to_dict("records"),
        }
        resultado["concentracion_top5"] = {
            "disponible": True,
            "datos": concentration_service.concentracion_top_n(licitaciones, 5).to_dict("records"),
        }

        if adendas is not None:
            resultado["low_balling"] = {
                "disponible": True,
                "datos": finanzas.low_balling_index(licitaciones, adendas).to_dict("records"),
            }

        aristas = network_service.aristas_desde_licitaciones(licitaciones)
        tabla_redes = network_service.metricas_por_entidad(aristas)
        resultado["redes"] = {"disponible": not tabla_redes.empty, "datos": tabla_redes.to_dict("records")}

        tabla_patrones = pattern_service.evaluar_patrones(licitaciones, ofertas, adendas, entidades)
        resultado["patrones"] = {"disponible": not tabla_patrones.empty, "datos": tabla_patrones.to_dict("records")}

        # Motor A (ml/scoring.py: Isolation Forest + LOF + DBSCAN) si hay
        # licitaciones suficientes para entrenar; si no, cae al
        # heurístico z-score — ver services/risk_service.componente_anomalias.
        # Se calcula una sola vez acá y se reusa para el IRCS, en vez de
        # entrenar el modelo dos veces por corrida.
        tabla_anomalias = risk_service.componente_anomalias(licitaciones, ofertas, adendas)
        resultado["anomalias"] = {
            "disponible": not tabla_anomalias.empty,
            "datos": tabla_anomalias.to_dict("records"),
        }

        tabla_ircs = risk_service.calcular_ircs_por_licitacion(
            licitaciones=licitaciones,
            concentracion_por_organismo=tabla_hhi,
            red_por_entidad=tabla_redes,
            patrones_por_licitacion=tabla_patrones,
            anomalias_por_licitacion=tabla_anomalias,
            indicadores_macro=indicadores_macro or [],
        )
        resultado["riesgo_ircs"] = {"disponible": not tabla_ircs.empty, "datos": tabla_ircs.to_dict("records")}

        _persistir_procurement_en_postgres(licitaciones, aristas, tabla_ircs)

    return resultado


def ejecutar_pipeline(
    path_ofertas: str | None = None,
    path_licitaciones: str | None = None,
    path_adendas: str | None = None,
    path_entidades: str | None = None,
    persistir: bool = True,
) -> dict:
    """Punto de entrada reusable: lo llaman tanto el CLI (`main`) como la
    API (`api/main.py`) y el cron diario (GitHub Actions / Railway Cron).
    Devuelve el dict de salida y, si `persistir=True`, lo escribe además
    en `dashboard/data.json` (para que el dashboard estático lo lea sin
    necesidad de golpear la API)."""
    indicadores_macro = ingerir_indicadores_macro()
    _persistir_indicadores_macro_en_postgres(indicadores_macro)
    salida = {
        "generado_en": pd.Timestamp.now("UTC").isoformat(),
        "indicadores_macro": indicadores_macro,
        "procurement": analizar_procurement(
            path_ofertas, path_licitaciones, path_adendas, path_entidades, indicadores_macro
        ),
        "reglas_scoring": scoring.explicar_reglas().to_dict("records"),
        "reglas_patrones": pattern_service.explicar_reglas().to_dict("records"),
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
    parser.add_argument("--entidades", help="CSV real de entidades (domicilio, representante_tecnico, ...) para REGLA-004/REGLA-005")
    args = parser.parse_args()
    ejecutar_pipeline(args.ofertas, args.licitaciones, args.adendas, args.entidades, persistir=True)


if __name__ == "__main__":
    main()
