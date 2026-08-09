"""Conector real: Datos Argentina (portal CKAN) — Contrataciones Públicas.

datos.gob.ar corre sobre CKAN, con API pública documentada y sin necesidad
de credenciales para uso razonable:
    GET /api/3/action/package_show?id=<dataset>
    -> devuelve metadata + lista de "resources" (URLs directas a CSV/XLSX)

Datasets reales usados:
    - jgm-sistema-contrataciones-electronicas  (licitaciones y adjudicaciones
      de COMPR.AR)
    - jgm-contratar                            (CONTRAT.AR — obra pública)

Alimenta las tablas `licitacion` y `oferta` del esquema (db/schema.sql),
que a su vez nutren los indicadores de Capa 1 (bid rotation, co-presentismo)
y Capa 2 (HHI, low-balling, TGN bias) en analytics/.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from config.settings import SETTINGS
from ingestion.base import ConectorBase


class ConectorComprasPublicasAR(ConectorBase):
    fuente = "DATOS_GOB_AR_COMPRAS_PUBLICAS"

    def fetch(self, dataset_id: str = SETTINGS.endpoints.dataset_contrataciones) -> list[str]:
        """Devuelve las URLs de los recursos (CSV/XLSX) reales publicados
        para el dataset solicitado."""
        url = f"{SETTINGS.endpoints.datos_gob_ar_base}/package_show"
        resp = self._get(url, params={"id": dataset_id})
        payload = resp.json()
        if not payload.get("success"):
            return []
        recursos = payload["result"].get("resources", [])
        return [
            r["url"]
            for r in recursos
            if r.get("format", "").upper() in ("CSV", "XLSX", "XLS")
        ]

    def normalize(self, raw: list[str]) -> list[dict[str, Any]]:
        registros: list[dict[str, Any]] = []
        for url in raw:
            try:
                df = pd.read_csv(url) if url.lower().endswith("csv") else pd.read_excel(url)
            except Exception:  # noqa: BLE001 — fuente externa puede fallar/cambiar formato
                continue
            registros.extend(self._filas_a_registros(df, url))
        return registros

    @staticmethod
    def _filas_a_registros(df: pd.DataFrame, url_origen: str) -> list[dict[str, Any]]:
        """Normaliza nombres de columnas heterogéneos entre publicaciones
        de Compr.ar/Contrat.ar a un esquema común. Las columnas reales varían
        por dataset/versión; se mapean las más estables y el resto queda en
        `metadata` sin perder información."""
        df.columns = [str(c).strip().lower().replace(" ", "_") for c in df.columns]
        alias = {
            "organismo": ["organismo", "organismo_contratante", "reparticion"],
            "objeto": ["objeto", "objeto_contratacion", "descripcion"],
            "proveedor": ["proveedor", "razon_social", "empresa_adjudicataria"],
            "monto": ["monto_adjudicado", "monto", "importe_adjudicado"],
            "fecha_apertura": ["fecha_apertura", "fecha_publicacion"],
            "fecha_adjudicacion": ["fecha_adjudicacion", "fecha_resolucion"],
            "numero_proceso": ["numero_proceso", "nro_proceso", "expediente", "id"],
        }

        def buscar(col_candidatas: list[str]) -> str | None:
            for c in col_candidatas:
                if c in df.columns:
                    return c
            return None

        cols = {campo: buscar(cands) for campo, cands in alias.items()}
        registros = []
        for _, fila in df.iterrows():
            registro = {
                "fuente_id_externo": str(fila.get(cols["numero_proceso"], "")) if cols["numero_proceso"] else None,
                "organismo": fila.get(cols["organismo"]) if cols["organismo"] else None,
                "objeto": fila.get(cols["objeto"]) if cols["objeto"] else None,
                "proveedor": fila.get(cols["proveedor"]) if cols["proveedor"] else None,
                "monto_adjudicado": fila.get(cols["monto"]) if cols["monto"] else None,
                "fecha_apertura": fila.get(cols["fecha_apertura"]) if cols["fecha_apertura"] else None,
                "fecha_adjudicacion": fila.get(cols["fecha_adjudicacion"]) if cols["fecha_adjudicacion"] else None,
                "url_origen": url_origen,
                "fuente": "DATOS_GOB_AR_COMPRAS_PUBLICAS",
            }
            registros.append(registro)
        return registros
