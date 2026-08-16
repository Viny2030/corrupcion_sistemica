"""ORM declarativo (SQLAlchemy 2.0) que mapea 1:1 las tablas reales de
`db/schema.sql`. Ver la nota de alcance en `database/__init__.py` sobre
por qué esto es un módulo distinto del paquete `models/` (Pydantic, para
la API) aunque comparta nombre.

Se mapean las 15 tablas del esquema para que el resto del código pueda
ORM-ear contra cualquiera de ellas, aunque `database/repositories.py` —
lo que efectivamente usa `pipeline.py` hoy— solo opera sobre las que ya
alimenta el flujo CSV -> pipeline: `entidad`, `licitacion`,
`indicador_macro`, `grafo_arista` y `score_riesgo`."""
from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import (
    BigInteger, Boolean, CheckConstraint, Date, DateTime, ForeignKey,
    Integer, Numeric, String, Text, UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Entidad(Base):
    __tablename__ = "entidad"

    entidad_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default="gen_random_uuid()")
    tipo: Mapped[str] = mapped_column(String(30), nullable=False)
    nombre: Mapped[str] = mapped_column(Text, nullable=False)
    identificador_fiscal: Mapped[str | None] = mapped_column(String(50))
    pais: Mapped[str | None] = mapped_column(String(80))
    jurisdiccion: Mapped[str | None] = mapped_column(String(120))
    domicilio: Mapped[str | None] = mapped_column(Text)
    lat: Mapped[float | None] = mapped_column(Numeric)
    lon: Mapped[float | None] = mapped_column(Numeric)
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, server_default="{}")
    fuente: Mapped[str] = mapped_column(String(60), nullable=False)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default="now()")
    actualizado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default="now()")

    __table_args__ = (
        CheckConstraint(
            "tipo IN ('EMPRESA','ORGANISMO_PUBLICO','FUNCIONARIO','DIPUTADO','SENADOR',"
            "'JUEZ','FISCAL','BROKER','PARTIDO_POLITICO','OFFSHORE')",
            name="entidad_tipo_check",
        ),
    )


class EntidadAlias(Base):
    __tablename__ = "entidad_alias"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    entidad_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("entidad.entidad_id"), nullable=False)
    entidad_relacionada_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("entidad.entidad_id"), nullable=False)
    metodo: Mapped[str] = mapped_column(String(40), nullable=False)
    score_similitud: Mapped[float] = mapped_column(Numeric(5, 4), nullable=False)
    evidencia: Mapped[dict] = mapped_column(JSONB, server_default="{}")
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default="now()")

    __table_args__ = (UniqueConstraint("entidad_id", "entidad_relacionada_id", "metodo"),)


class Licitacion(Base):
    __tablename__ = "licitacion"

    licitacion_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default="gen_random_uuid()")
    fuente_id_externo: Mapped[str | None] = mapped_column(String(120))
    organismo_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("entidad.entidad_id"), nullable=False)
    objeto: Mapped[str | None] = mapped_column(Text)
    rubro: Mapped[str | None] = mapped_column(String(120))
    presupuesto_oficial: Mapped[float | None] = mapped_column(Numeric(18, 2))
    fecha_apertura: Mapped[date | None] = mapped_column(Date)
    fecha_adjudicacion: Mapped[date | None] = mapped_column(Date)
    monto_adjudicado: Mapped[float | None] = mapped_column(Numeric(18, 2))
    monto_ejecutado_final: Mapped[float | None] = mapped_column(Numeric(18, 2))
    modalidad: Mapped[str | None] = mapped_column(String(60))
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, server_default="{}")
    fuente: Mapped[str] = mapped_column(String(60), nullable=False)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default="now()")


class Oferta(Base):
    __tablename__ = "oferta"

    oferta_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default="gen_random_uuid()")
    licitacion_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("licitacion.licitacion_id"), nullable=False)
    empresa_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("entidad.entidad_id"), nullable=False)
    monto_ofertado: Mapped[float | None] = mapped_column(Numeric(18, 2))
    porcentaje_sobre_ganadora: Mapped[float | None] = mapped_column(Numeric(8, 4))
    resultado: Mapped[str | None] = mapped_column(String(20))
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default="now()")

    __table_args__ = (
        UniqueConstraint("licitacion_id", "empresa_id"),
        CheckConstraint("resultado IN ('GANADORA','PERDEDORA','DESCALIFICADA')", name="oferta_resultado_check"),
    )


class Adenda(Base):
    __tablename__ = "adenda"

    adenda_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default="gen_random_uuid()")
    licitacion_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("licitacion.licitacion_id"), nullable=False)
    fecha: Mapped[date | None] = mapped_column(Date)
    monto_original: Mapped[float | None] = mapped_column(Numeric(18, 2))
    monto_nuevo: Mapped[float | None] = mapped_column(Numeric(18, 2))
    motivo: Mapped[str | None] = mapped_column(Text)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default="now()")


class PagoTGN(Base):
    __tablename__ = "pago_tgn"

    pago_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default="gen_random_uuid()")
    licitacion_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("licitacion.licitacion_id"))
    empresa_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("entidad.entidad_id"), nullable=False)
    organismo_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("entidad.entidad_id"), nullable=False)
    fecha_factura: Mapped[date | None] = mapped_column(Date)
    fecha_pago: Mapped[date | None] = mapped_column(Date)
    dias_habiles_pago: Mapped[int | None] = mapped_column(Integer)
    monto: Mapped[float | None] = mapped_column(Numeric(18, 2))
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default="now()")


class AporteCampana(Base):
    __tablename__ = "aporte_campana"

    aporte_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default="gen_random_uuid()")
    aportante_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("entidad.entidad_id"), nullable=False)
    partido_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("entidad.entidad_id"), nullable=False)
    eleccion: Mapped[str | None] = mapped_column(String(60))
    monto: Mapped[float | None] = mapped_column(Numeric(18, 2))
    fecha: Mapped[date | None] = mapped_column(Date)
    fuente: Mapped[str] = mapped_column(String(60), nullable=False)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default="now()")


class Votacion(Base):
    __tablename__ = "votacion"

    votacion_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default="gen_random_uuid()")
    camara: Mapped[str | None] = mapped_column(String(20))
    expediente: Mapped[str | None] = mapped_column(String(80))
    titulo: Mapped[str | None] = mapped_column(Text)
    fecha: Mapped[date | None] = mapped_column(Date)
    resultado: Mapped[str | None] = mapped_column(String(30))
    fuente: Mapped[str] = mapped_column(String(60), nullable=False)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default="now()")

    __table_args__ = (CheckConstraint("camara IN ('DIPUTADOS','SENADORES')", name="votacion_camara_check"),)


class VotoIndividual(Base):
    __tablename__ = "voto_individual"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    votacion_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("votacion.votacion_id"), nullable=False)
    legislador_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("entidad.entidad_id"), nullable=False)
    voto: Mapped[str | None] = mapped_column(String(20))

    __table_args__ = (
        CheckConstraint("voto IN ('AFIRMATIVO','NEGATIVO','ABSTENCION','AUSENTE')", name="voto_individual_voto_check"),
    )


class CausaJudicial(Base):
    __tablename__ = "causa_judicial"

    causa_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default="gen_random_uuid()")
    caratula: Mapped[str | None] = mapped_column(Text)
    fuero: Mapped[str | None] = mapped_column(String(80))
    jurisdiccion: Mapped[str | None] = mapped_column(String(80))
    fecha_inicio: Mapped[date | None] = mapped_column(Date)
    fecha_resolucion: Mapped[date | None] = mapped_column(Date)
    estado: Mapped[str | None] = mapped_column(String(40))
    texto_fallo: Mapped[str | None] = mapped_column(Text)
    juez_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("entidad.entidad_id"))
    fuente: Mapped[str] = mapped_column(String(60), nullable=False)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default="now()")


class Imputado(Base):
    __tablename__ = "imputado"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    causa_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("causa_judicial.causa_id"), nullable=False)
    entidad_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("entidad.entidad_id"), nullable=False)
    rango_jerarquico: Mapped[str | None] = mapped_column(String(40))
    condena_meses: Mapped[int | None] = mapped_column(Integer)
    monto_multa: Mapped[float | None] = mapped_column(Numeric(18, 2))


class AuditoriaCompliance(Base):
    __tablename__ = "auditoria_compliance"

    auditoria_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default="gen_random_uuid()")
    empresa_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("entidad.entidad_id"), nullable=False)
    fecha: Mapped[date | None] = mapped_column(Date)
    tiene_programa_integridad: Mapped[bool | None] = mapped_column(Boolean)
    score_efectividad: Mapped[float | None] = mapped_column(Numeric(5, 2))
    hallazgos: Mapped[dict] = mapped_column(JSONB, server_default="{}")
    fuente: Mapped[str] = mapped_column(String(60), nullable=False, server_default="MEACI")


class GrafoArista(Base):
    __tablename__ = "grafo_arista"

    arista_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    origen_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("entidad.entidad_id"), nullable=False)
    destino_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("entidad.entidad_id"), nullable=False)
    tipo_relacion: Mapped[str] = mapped_column(String(40), nullable=False)
    peso: Mapped[float] = mapped_column(Numeric(12, 4), server_default="1.0")
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, server_default="{}")
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default="now()")


class IndicadorMacro(Base):
    __tablename__ = "indicador_macro"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    pais_iso3: Mapped[str] = mapped_column(String(3), nullable=False)
    anio: Mapped[int] = mapped_column(Integer, nullable=False)
    indicador: Mapped[str] = mapped_column(String(40), nullable=False)
    valor: Mapped[float | None] = mapped_column(Numeric(10, 4))
    fuente: Mapped[str] = mapped_column(String(60), nullable=False)

    __table_args__ = (UniqueConstraint("pais_iso3", "anio", "indicador"),)


class ScoreRiesgo(Base):
    __tablename__ = "score_riesgo"

    score_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default="gen_random_uuid()")
    entidad_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("entidad.entidad_id"))
    licitacion_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("licitacion.licitacion_id"))
    capa: Mapped[str] = mapped_column(String(20), nullable=False)
    score: Mapped[float] = mapped_column(Numeric(6, 2), nullable=False)
    desglose: Mapped[dict] = mapped_column(JSONB, nullable=False)
    calculado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default="now()")
