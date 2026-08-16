"""`/api/v1/documentos` — NLP sobre el Boletín Oficial
(`services/nlp_service.py`): extrae personas, empresas, organismos,
CUIT, montos y expedientes de un texto real (título o cuerpo de un
aviso, decreto o resolución).

No persiste los documentos procesados: cada request corre el extractor
sobre el texto que se le pase, sin guardar el resultado. Sumar una tabla
para persistirlos implicaría una migración de `db/schema.sql` — se deja
para una fase siguiente en vez de decidirlo unilateralmente acá."""
from __future__ import annotations

from fastapi import APIRouter

from schemas.documento import DocumentoIn, DocumentoProcesado
from services import nlp_service

router = APIRouter(prefix="/documentos", tags=["documentos"])


@router.post("/procesar", response_model=DocumentoProcesado)
def procesar_documento(payload: DocumentoIn) -> dict:
    """Acepta texto plano (título o cuerpo de un aviso real, ya extraído
    por `ingestion/bora_boletin.py` u otra fuente) y devuelve las
    entidades reales detectadas. PDF/DOCX/OCR (mencionados en la
    arquitectura objetivo) quedan fuera de este endpoint: convertí a
    texto antes de llamarlo — ver README > "NLP sobre el Boletín
    Oficial"."""
    return nlp_service.extraer_entidades(payload.texto, payload.documento)
