"""Agrega todos los routers de `/api/v1` en uno solo, montado desde
`api/main.py` con `app.include_router(router)`."""
from __future__ import annotations

from fastapi import APIRouter

from api.v1 import alertas, contratos, documentos, empresas, patrones, redes, riesgo

router = APIRouter(prefix="/api/v1")
router.include_router(contratos.router)
router.include_router(empresas.router)
router.include_router(redes.router)
router.include_router(patrones.router)
router.include_router(riesgo.router)
router.include_router(alertas.router)
router.include_router(documentos.router)
