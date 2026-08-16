"""Schemas de entrada/salida para `/api/v1/documentos` (NLP sobre el Boletín Oficial, `services/nlp_service.py`)."""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class DocumentoIn(BaseModel):
    texto: str
    documento: Optional[str] = None


class EntidadExtraida(BaseModel):
    tipo: str
    nombre: str


class DocumentoProcesado(BaseModel):
    documento: Optional[str] = None
    motor_personas: Optional[str] = None
    entidades: list[EntidadExtraida]
