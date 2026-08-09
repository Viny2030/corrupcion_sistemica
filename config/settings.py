"""
Configuración central del Mapa de Transparencia.

Todos los endpoints listados abajo son fuentes públicas reales. Ninguno
requiere simulación de datos: si una fuente no tiene API pública abierta
(ej. BORA, Poder Judicial), el conector correspondiente implementa scraping
o deja un punto de extensión documentado, pero nunca genera datos ficticios.
"""

import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Endpoints:
    # Transparency International — Corruption Perceptions Index (CPI)
    # Publica un CSV/Excel anual descargable públicamente.
    cpi_landing: str = "https://www.transparency.org/en/cpi/"

    # World Bank — Worldwide Governance Indicators (WGI), vía API de datos abiertos.
    # Indicador CC.EST = Control of Corruption: Estimate
    wgi_api_base: str = "https://api.worldbank.org/v2/country/{country}/indicator/{indicator}"

    # Datos Argentina — Sistema de Contrataciones Electrónicas / Compr.ar / Contrat.ar
    datos_gob_ar_base: str = "https://datos.gob.ar/api/3/action"
    dataset_contrataciones: str = "jgm-sistema-contrataciones-electronicas"
    dataset_contratar: str = "jgm-contratar"

    # HCDN — Diputados: portal de datos abiertos y consulta de votaciones
    hcdn_datos_abiertos: str = "https://datos.hcdn.gob.ar"
    hcdn_votaciones: str = "https://votaciones.hcdn.gob.ar"

    # Senado — datos abiertos (portal institucional, sin API REST estable;
    # se documenta como fuente de descarga manual/scraping controlado)
    senado_datos_abiertos: str = "https://www.senado.gob.ar/parlamentario/parlamentaria/votaciones"

    # Boletín Oficial de la República Argentina — buscador público (sin API oficial)
    bora_buscador: str = "https://www.boletinoficial.gob.ar/busquedaAvanzada/primera"

    # SAIJ (Sistema Argentino de Información Jurídica) — buscador de jurisprudencia
    saij_buscador: str = "http://www.saij.gob.ar/busqueda"


@dataclass(frozen=True)
class DBConfig:
    host: str = os.getenv("PG_HOST", "localhost")
    port: int = int(os.getenv("PG_PORT", "5432"))
    dbname: str = os.getenv("PG_DB", "mapa_transparencia")
    user: str = os.getenv("PG_USER", "postgres")
    password: str = os.getenv("PG_PASSWORD", "")

    @property
    def dsn(self) -> str:
        return (
            f"postgresql+psycopg2://{self.user}:{self.password}"
            f"@{self.host}:{self.port}/{self.dbname}"
        )


@dataclass(frozen=True)
class Settings:
    endpoints: Endpoints = field(default_factory=Endpoints)
    db: DBConfig = field(default_factory=DBConfig)
    request_timeout_s: int = 30
    user_agent: str = "MapaTransparencia/1.0 (+investigacion academica sin fines comerciales)"
    paises_comparables_iso3: tuple = ("ARG", "BRA", "CHL", "URY", "COL", "MEX")


SETTINGS = Settings()
