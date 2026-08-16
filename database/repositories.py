"""Repositorios: funciones de persistencia idempotentes contra Postgres
(ver db/schema.sql), usadas por `pipeline.py` cuando hay conexión real
disponible (`database.connection.verificar_conexion()`). Si no la hay,
el pipeline sigue funcionando igual con `dashboard/data.json` como única
salida — ver la nota de alcance en `database/__init__.py`.

Las funciones de upsert de entidades buscan primero por
`identificador_fiscal` (si está) o por `(nombre, tipo)` antes de
insertar, para no duplicar el mismo organismo/empresa en corridas
sucesivas del pipeline sobre el mismo CSV. `persistir_licitaciones` es
idempotente por `fuente_id_externo` (el `licitacion_id` del CSV de
origen)."""
from __future__ import annotations

import logging
from typing import Optional

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from database.models import Entidad, GrafoArista, IndicadorMacro, Licitacion, ScoreRiesgo

logger = logging.getLogger("corrupcion_sistemica.database")


def obtener_o_crear_entidad(
    session: Session,
    nombre: str,
    tipo: str,
    fuente: str,
    identificador_fiscal: Optional[str] = None,
    domicilio: Optional[str] = None,
) -> Entidad:
    if identificador_fiscal:
        consulta = select(Entidad).where(Entidad.identificador_fiscal == identificador_fiscal)
    else:
        consulta = select(Entidad).where(Entidad.nombre == nombre, Entidad.tipo == tipo)

    existente = session.execute(consulta).scalars().first()
    if existente:
        return existente

    entidad = Entidad(nombre=nombre, tipo=tipo, fuente=fuente, identificador_fiscal=identificador_fiscal, domicilio=domicilio)
    session.add(entidad)
    session.flush()  # asigna entidad_id sin cerrar la transacción
    return entidad


def upsert_entidades_de_licitaciones(session: Session, licitaciones: pd.DataFrame, fuente: str = "pipeline") -> dict[str, Entidad]:
    """Crea (si no existen) una entidad ORGANISMO_PUBLICO por cada
    `organismo` y una EMPRESA por cada `proveedor` únicos en
    `licitaciones`. Devuelve un mapa nombre -> Entidad para resolver las
    foreign keys al persistir las licitaciones/aristas."""
    mapa: dict[str, Entidad] = {}
    if "organismo" in licitaciones.columns:
        for organismo in licitaciones["organismo"].dropna().unique():
            mapa[organismo] = obtener_o_crear_entidad(session, str(organismo), "ORGANISMO_PUBLICO", fuente)
    if "proveedor" in licitaciones.columns:
        for proveedor in licitaciones["proveedor"].dropna().unique():
            mapa[proveedor] = obtener_o_crear_entidad(session, str(proveedor), "EMPRESA", fuente)
    return mapa


def persistir_licitaciones(
    session: Session, licitaciones: pd.DataFrame, entidades: dict[str, Entidad], fuente: str = "pipeline"
) -> dict[str, Licitacion]:
    """Idempotente por `fuente_id_externo` (el `licitacion_id` del CSV):
    si ya existe una licitación con ese id externo, se actualiza en vez
    de duplicarla. Licitaciones cuyo `organismo` no se pudo resolver a
    una entidad se saltean (no se inventa un organismo)."""
    mapa: dict[str, Licitacion] = {}
    for _, fila in licitaciones.iterrows():
        id_externo = str(fila.get("licitacion_id"))
        organismo = entidades.get(fila.get("organismo"))
        if organismo is None:
            logger.warning("Licitación %s sin organismo resoluble; se saltea.", id_externo)
            continue

        datos = dict(
            fuente_id_externo=id_externo,
            organismo_id=organismo.entidad_id,
            objeto=fila.get("objeto"),
            rubro=fila.get("rubro"),
            presupuesto_oficial=_a_float(fila.get("presupuesto_oficial")),
            fecha_apertura=_a_fecha(fila.get("fecha_apertura")),
            fecha_adjudicacion=_a_fecha(fila.get("fecha_adjudicacion")),
            monto_adjudicado=_a_float(fila.get("monto_adjudicado")),
            modalidad=fila.get("modalidad"),
            fuente=fuente,
        )

        existente = session.execute(select(Licitacion).where(Licitacion.fuente_id_externo == id_externo)).scalars().first()
        if existente:
            for campo, valor in datos.items():
                setattr(existente, campo, valor)
            mapa[id_externo] = existente
        else:
            nueva = Licitacion(**datos)
            session.add(nueva)
            session.flush()
            mapa[id_externo] = nueva
    return mapa


def persistir_indicadores_macro(session: Session, indicadores: list[dict]) -> None:
    """Idempotente por `(pais_iso3, anio, indicador)` — coincide con el
    UNIQUE real de la tabla."""
    for ind in indicadores:
        if not all(k in ind for k in ("pais_iso3", "anio", "indicador")):
            continue
        existente = session.execute(
            select(IndicadorMacro).where(
                IndicadorMacro.pais_iso3 == ind["pais_iso3"],
                IndicadorMacro.anio == ind["anio"],
                IndicadorMacro.indicador == ind["indicador"],
            )
        ).scalars().first()
        if existente:
            existente.valor = ind.get("valor")
            existente.fuente = ind.get("fuente", existente.fuente)
        else:
            session.add(IndicadorMacro(
                pais_iso3=ind["pais_iso3"], anio=ind["anio"], indicador=ind["indicador"],
                valor=ind.get("valor"), fuente=ind.get("fuente", "pipeline"),
            ))


def persistir_grafo_aristas(
    session: Session, aristas: pd.DataFrame, entidades: dict[str, Entidad], tipo_relacion: str = "ADJUDICACION"
) -> int:
    """Inserta una arista por fila de `aristas` (columnas origen_id,
    destino_id, peso — ver `services/network_service.aristas_desde_licitaciones`).
    No es idempotente (se re-insertan en cada corrida): `grafo_arista` no
    tiene una clave natural única en el esquema real para deduplicar
    contra corridas anteriores sin agregar una migración; se documenta
    como limitación conocida en el README."""
    insertadas = 0
    for _, fila in aristas.iterrows():
        origen = entidades.get(fila["origen_id"])
        destino = entidades.get(fila["destino_id"])
        if origen is None or destino is None:
            continue
        session.add(GrafoArista(
            origen_id=origen.entidad_id, destino_id=destino.entidad_id,
            tipo_relacion=tipo_relacion, peso=float(fila.get("peso") or 1.0),
        ))
        insertadas += 1
    return insertadas


def persistir_scores_riesgo(
    session: Session, tabla_ircs: pd.DataFrame, licitaciones_por_id_externo: dict[str, Licitacion]
) -> int:
    """Un `score_riesgo` (capa='TOTAL') por licitación con IRCS
    calculado. Tampoco es idempotente por el mismo motivo que las
    aristas — cada corrida agrega una fila nueva, lo cual además sirve
    como historial de cómo evolucionó el score en corridas sucesivas."""
    insertados = 0
    for _, fila in tabla_ircs.iterrows():
        licitacion = licitaciones_por_id_externo.get(str(fila.get("licitacion_id")))
        if licitacion is None or fila.get("ircs") is None:
            continue
        session.add(ScoreRiesgo(
            licitacion_id=licitacion.licitacion_id,
            capa="TOTAL",
            score=float(fila["ircs"]),
            desglose=fila.get("ircs_componentes") or {},
        ))
        insertados += 1
    return insertados


def _a_float(valor) -> Optional[float]:
    try:
        if valor is None or (isinstance(valor, float) and pd.isna(valor)):
            return None
        return float(valor)
    except (TypeError, ValueError):
        return None


def _a_fecha(valor):
    if valor is None or (isinstance(valor, float) and pd.isna(valor)):
        return None
    fecha = pd.to_datetime(valor, errors="coerce")
    return fecha.date() if pd.notna(fecha) else None
