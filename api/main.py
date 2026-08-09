"""API REST del Mapa de Transparencia — servicio autónomo (futuro "Monitor
12" del ecosistema Mapa de Transparencia).

Diseño: este módulo corre como servicio independiente en Railway. Expone
endpoints para que el hub central del Mapa de Transparencia (u otro
consumidor) consulte indicadores reales y dispare/lea corridas del
pipeline, sin acoplarse al resto del ecosistema (arquitectura satélite,
igual que los otros sensores: COMPRAR TGN, MONITOR CONTRATOS, etc.).

Incluye un scheduler en proceso (APScheduler) que corre `pipeline.py`
periódicamente, para que el servicio sea autónomo también si no se usa
el Cron Job nativo de Railway (ver README > Despliegue en Railway).
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from analytics import scoring
from pipeline import DIR_DASHBOARD, ejecutar_pipeline

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("mapa_transparencia.api")

VERSION = "1.0.0"
NOMBRE_MODULO = "Monitor 12 — Mapa de Transparencia (Corrupción Sistémica)"
INTERVALO_HORAS = float(os.getenv("PIPELINE_INTERVAL_HOURS", "24"))
ALLOWED_ORIGINS = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "*").split(",")]

app = FastAPI(
    title=NOMBRE_MODULO,
    version=VERSION,
    description="Servicio autónomo de análisis de corrupción sistémica sobre datos reales.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)

ESTADO = {"ultima_corrida": None, "ultima_corrida_ok": None, "corridas": 0}
scheduler = BackgroundScheduler(timezone="UTC")


def _job_pipeline() -> None:
    try:
        ejecutar_pipeline(persistir=True)
        ESTADO["ultima_corrida"] = datetime.now(timezone.utc).isoformat()
        ESTADO["ultima_corrida_ok"] = True
        ESTADO["corridas"] += 1
        logger.info("Corrida programada del pipeline OK (#%s)", ESTADO["corridas"])
    except Exception as exc:  # noqa: BLE001 — no debe tumbar el scheduler
        ESTADO["ultima_corrida"] = datetime.now(timezone.utc).isoformat()
        ESTADO["ultima_corrida_ok"] = False
        logger.exception("Corrida programada del pipeline falló: %s", exc)


@app.on_event("startup")
def iniciar_scheduler() -> None:
    if os.getenv("DESHABILITAR_SCHEDULER", "").lower() in ("1", "true"):
        logger.info("Scheduler interno deshabilitado por variable de entorno.")
        return
    scheduler.add_job(
        _job_pipeline,
        "interval",
        hours=INTERVALO_HORAS,
        id="pipeline_periodico",
        next_run_time=datetime.now(timezone.utc),  # corre una vez al arrancar
    )
    scheduler.start()
    logger.info("Scheduler interno iniciado: pipeline cada %s horas.", INTERVALO_HORAS)


@app.on_event("shutdown")
def detener_scheduler() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)


def _leer_data_json() -> dict:
    destino = DIR_DASHBOARD / "data.json"
    if not destino.exists():
        return {"indicadores_macro": [], "procurement": {}, "generado_en": None}
    return json.loads(destino.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/")
def info() -> dict:
    return {
        "modulo": NOMBRE_MODULO,
        "version": VERSION,
        "estado_scheduler": ESTADO,
        "intervalo_horas": INTERVALO_HORAS,
    }


@app.get("/health")
def health() -> dict:
    """Healthcheck para Railway (configurar como healthcheckPath)."""
    return {"status": "ok"}


@app.get("/indicadores/macro")
def indicadores_macro(pais_iso3: Optional[str] = None, indicador: Optional[str] = None) -> list[dict]:
    """CPI / WGI reales, ya ingeridos por el pipeline. Filtra opcionalmente
    por país (ISO3) y/o nombre de indicador."""
    datos = _leer_data_json().get("indicadores_macro", [])
    if pais_iso3:
        datos = [d for d in datos if d.get("pais_iso3") == pais_iso3.upper()]
    if indicador:
        datos = [d for d in datos if d.get("indicador") == indicador]
    return datos


@app.get("/procurement/{bloque}")
def procurement(bloque: str) -> dict:
    """Bloques disponibles: co_presentismo, asimetria_victorias,
    hhi_por_organismo, low_balling."""
    datos = _leer_data_json().get("procurement", {})
    return datos.get(bloque, {"disponible": False, "datos": [], "error": "bloque desconocido"})


@app.get("/scoring/reglas")
def scoring_reglas() -> list[dict]:
    return scoring.explicar_reglas().to_dict("records")


class FilaIndicadores(BaseModel):
    """Fila de indicadores ya calculados para una licitación/empresa, tal
    como la producen analytics/finanzas.py y analytics/sna.py. Todos los
    campos son opcionales: el motor de scoring solo activa las reglas para
    las que haya evidencia real presente."""

    alta_concentracion: Optional[bool] = None
    low_balling_ratio: Optional[float] = None
    priorizacion_detectada: Optional[bool] = None
    dias_ahorrados: Optional[float] = None
    indice_alternancia: Optional[float] = None
    compliance_de_papel: Optional[bool] = None


@app.post("/scoring/evaluar")
def scoring_evaluar(fila: FilaIndicadores) -> dict:
    """Calcula el score de riesgo + audit card (XAI) para una fila real de
    indicadores. Pensado para que el hub central del Mapa de Transparencia
    consulte este endpoint por contrato/empresa."""
    import pandas as pd

    return scoring.calcular_score(pd.Series(fila.model_dump()))


@app.post("/pipeline/ejecutar")
async def pipeline_ejecutar(
    ofertas: Optional[UploadFile] = None,
    licitaciones: Optional[UploadFile] = None,
    adendas: Optional[UploadFile] = None,
) -> dict:
    """Dispara una corrida manual del pipeline. Si se adjuntan CSV reales
    de ofertas/licitaciones/adendas, corre también Capa 1 y Capa 2 sobre
    ellos; si no, solo actualiza los indicadores macro (CPI/WGI)."""
    tmp_dir = Path(tempfile.mkdtemp(prefix="mapa_transparencia_"))
    rutas = {}
    try:
        for nombre, archivo in (("ofertas", ofertas), ("licitaciones", licitaciones), ("adendas", adendas)):
            if archivo is not None:
                destino = tmp_dir / archivo.filename
                with destino.open("wb") as f:
                    shutil.copyfileobj(archivo.file, f)
                rutas[nombre] = str(destino)

        resultado = ejecutar_pipeline(
            path_ofertas=rutas.get("ofertas"),
            path_licitaciones=rutas.get("licitaciones"),
            path_adendas=rutas.get("adendas"),
            persistir=True,
        )
        ESTADO["ultima_corrida"] = datetime.now(timezone.utc).isoformat()
        ESTADO["ultima_corrida_ok"] = True
        ESTADO["corridas"] += 1
        return resultado
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
