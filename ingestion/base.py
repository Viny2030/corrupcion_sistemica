"""Clase base para todos los conectores de ingesta."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any

import requests

from config.settings import SETTINGS

logger = logging.getLogger("mapa_transparencia.ingestion")


class ConectorBase(ABC):
    """Contrato común: fetch() devuelve datos crudos, normalize() los deja
    en forma tabular (lista de dicts / DataFrame) lista para persistir.
    Ningún conector debe inventar registros: si la fuente no responde o
    no tiene datos, se propaga una lista vacía o la excepción, nunca datos
    ficticios.
    """

    fuente: str = "SIN_DEFINIR"

    def __init__(self, session: requests.Session | None = None) -> None:
        self.session = session or requests.Session()
        self.session.headers.update({"User-Agent": SETTINGS.user_agent})

    def _get(self, url: str, **kwargs: Any) -> requests.Response:
        timeout = kwargs.pop("timeout", SETTINGS.request_timeout_s)
        logger.info("GET %s", url)
        resp = self.session.get(url, timeout=timeout, **kwargs)
        resp.raise_for_status()
        return resp

    @abstractmethod
    def fetch(self, *args: Any, **kwargs: Any) -> Any:
        """Obtiene los datos crudos desde la fuente real."""

    @abstractmethod
    def normalize(self, raw: Any) -> list[dict]:
        """Transforma los datos crudos al esquema normalizado interno."""

    def run(self, *args: Any, **kwargs: Any) -> list[dict]:
        raw = self.fetch(*args, **kwargs)
        return self.normalize(raw)
