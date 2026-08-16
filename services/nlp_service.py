"""Motor de NLP sobre el Boletín Oficial (y cualquier texto real de
avisos/decretos/resoluciones): extrae personas, empresas, organismos,
CUIT, montos y expedientes reales — el paso "NER" de la arquitectura
objetivo, para poblar el Knowledge Graph (tabla `entidad` de
db/schema.sql) a partir del texto que ya trae `ingestion/bora_boletin.py`
u otra fuente real (el título de cada aviso hoy, o el cuerpo completo si
en una fase siguiente el conector llega a buscarlo por URL).

Igual que `analytics/judicial_nlp.py`, se prioriza una heurística
transparente y auditable sobre una caja negra:

- **CUIT, montos y expedientes** salen siempre de expresiones regulares
  deterministas — no hay ambigüedad posible en su formato.
- **Personas** se detectan con el modelo NER de spaCy (`es_core_news_sm`)
  si está instalado, porque para nombres propios funciona razonablemente
  bien incluso en su versión "small"; si no está instalado, cae a una
  heurística de títulos (Sr./Dra./Lic. + nombre capitalizado).
- **Empresas y organismos** NO se delegan al NER genérico de spaCy: en
  pruebas sobre texto real de avisos oficiales, el modelo "small" en
  español confunde sistemáticamente ORG con LOC (verificado en esta
  sesión — "Ministerio de Economía" y "Empresa XYZ S.A." salen
  etiquetados como LOC, no ORG). Por eso ambos usan reglas léxicas
  propias: sufijos societarios (S.A., S.R.L., UTE, ...) para empresas, y
  palabras clave + siglas conocidas de la administración pública para
  organismos. Es más angosto que un NER genérico, pero no arrastra ese
  sesgo conocido.
"""
from __future__ import annotations

import re
from functools import lru_cache
from typing import Optional

PATRON_CUIT = re.compile(r"\b\d{2}-\d{7,8}-\d\b")

PATRON_EXPEDIENTE = re.compile(r"\bEX-\d{4}-\d{6,10}-\s*-?[A-Z]{2,10}[\w#-]*\b")

PATRON_MONTO = re.compile(r"(?:\$|PESOS)\s?[\d\.]{1,15}(?:,\d{1,2})?", re.I)

_SUFIJOS_EMPRESA = [
    r"S\.?A\.?", r"S\.?R\.?L\.?", r"S\.?A\.?S\.?", r"S\.?A\.?C\.?I\.?",
    r"S\.?C\.?A\.?", r"U\.?T\.?E\.?",
]
PATRON_EMPRESA = re.compile(
    r"\b((?:[A-ZÁÉÍÓÚÑ][\wÁÉÍÓÚÑ.&\-]*\s){1,6}(?:" + "|".join(_SUFIJOS_EMPRESA) + r"))\b"
)

_PALABRAS_ORGANISMO = [
    "Ministerio", r"Secretar[ií]a", r"Subsecretar[ií]a", r"Direcci[oó]n Nacional",
    r"Direcci[oó]n General", "Instituto Nacional", r"Administraci[oó]n Nacional",
    r"Administraci[oó]n Federal", "Agencia Nacional", "Ente Nacional",
    "Jefatura de Gabinete", r"Presidencia de la Naci[oó]n", "Poder Ejecutivo Nacional",
    r"Sindicatura General", r"Auditoría General", "Superintendencia",
]
# Las palabras clave (Ministerio, Secretaría, ...) y los conectores (de,
# del, nacional) se buscan sin distinguir mayúsculas/minúsculas
# ((?i: ... ) inline), pero la clase [A-ZÁÉÍÓÚÑ] que exige mayúscula
# inicial en cada palabra siguiente SÍ debe quedar sensible a mayúsculas
# — por eso no se usa el flag re.I global acá (con re.I, [A-Z] también
# matchea minúsculas y el patrón se vuelve demasiado goloso).
PATRON_ORGANISMO = re.compile(
    r"\b((?:(?i:" + "|".join(_PALABRAS_ORGANISMO) + r"))"
    r"(?:\s+(?:(?i:de|del|nacional))?\s*[A-ZÁÉÍÓÚÑ][\wÁÉÍÓÚÑ]*){0,6})"
)
SIGLAS_ORGANISMO_CONOCIDAS = {
    "ANSES", "AFIP", "PAMI", "INDEC", "ANMAT", "SENASA", "RENAPER", "AABE",
    "ONABE", "IGJ", "CNV", "BCRA",
}

_TITULOS_PERSONA = [r"Sr\.", r"Sra\.", r"Dr\.", r"Dra\.", r"Lic\.", r"Ing\.", r"Cdor\.", r"Cdora\."]
PATRON_PERSONA_HEURISTICA = re.compile(
    r"\b(?:" + "|".join(_TITULOS_PERSONA) + r")\s+([A-ZÁÉÍÓÚÑ][a-záéíóúñ]+(?:\s+[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+){1,3})"
)


def _normalizar_espacios(texto: str) -> str:
    """Colapsa saltos de línea/espacios múltiples a un solo espacio antes
    de aplicar las expresiones regulares — sin esto, un nombre de
    empresa u organismo partido en dos líneas por el HTML/PDF de origen
    no matchea."""
    return re.sub(r"\s+", " ", texto or "").strip()


@lru_cache(maxsize=1)
def _cargar_modelo_spacy():
    """Carga perezosa y cacheada de `es_core_news_sm`. Devuelve `None` si
    spaCy o el modelo no están instalados, sin lanzar excepción — el
    resto del módulo cae a la heurística de personas en ese caso (mismo
    patrón de try/except silencioso que `analytics/sna.py` usa para
    `python-louvain`)."""
    try:
        import spacy

        return spacy.load("es_core_news_sm")
    except Exception:
        return None


def extraer_cuit(texto: str) -> list[str]:
    return sorted(set(PATRON_CUIT.findall(_normalizar_espacios(texto))))


def extraer_montos(texto: str) -> list[str]:
    return sorted({m.strip() for m in PATRON_MONTO.findall(_normalizar_espacios(texto))})


def extraer_expedientes(texto: str) -> list[str]:
    return sorted(set(PATRON_EXPEDIENTE.findall(_normalizar_espacios(texto))))


def extraer_empresas(texto: str) -> list[str]:
    return sorted({m.strip() for m in PATRON_EMPRESA.findall(_normalizar_espacios(texto))})


def extraer_organismos(texto: str) -> list[str]:
    texto_normalizado = _normalizar_espacios(texto)
    encontrados = {m.strip() for m in PATRON_ORGANISMO.findall(texto_normalizado)}
    for sigla in SIGLAS_ORGANISMO_CONOCIDAS:
        if re.search(rf"\b{sigla}\b", texto_normalizado):
            encontrados.add(sigla)
    return sorted(encontrados)


def extraer_personas(texto: str) -> tuple[list[str], str]:
    """Devuelve `(personas, motor_usado)` — `motor_usado` queda expuesto
    en `extraer_entidades` para que quien consuma la API sepa si el
    resultado viene del modelo de spaCy o de la heurística de respaldo."""
    texto_normalizado = _normalizar_espacios(texto)
    modelo = _cargar_modelo_spacy()
    if modelo is not None:
        doc = modelo(texto_normalizado)
        personas = sorted({ent.text.strip() for ent in doc.ents if ent.label_ == "PER"})
        return personas, "spacy_es_core_news_sm"

    personas = sorted({m.strip() for m in PATRON_PERSONA_HEURISTICA.findall(texto_normalizado)})
    return personas, "heuristico_titulos"


def extraer_entidades(texto: str, documento: Optional[str] = None) -> dict:
    """Punto de entrada principal: corre los 6 extractores reales sobre
    `texto` (el cuerpo o título de un aviso/decreto/resolución real) y
    devuelve el resultado en el formato de la arquitectura objetivo —
    ver `api/v1/documentos.py`."""
    if not texto or not texto.strip():
        return {"documento": documento, "motor_personas": None, "entidades": []}

    personas, motor_personas = extraer_personas(texto)

    entidades = (
        [{"tipo": "persona", "nombre": p} for p in personas]
        + [{"tipo": "empresa", "nombre": e} for e in extraer_empresas(texto)]
        + [{"tipo": "organismo", "nombre": o} for o in extraer_organismos(texto)]
        + [{"tipo": "cuit", "nombre": c} for c in extraer_cuit(texto)]
        + [{"tipo": "monto", "nombre": m} for m in extraer_montos(texto)]
        + [{"tipo": "expediente", "nombre": e} for e in extraer_expedientes(texto)]
    )

    return {"documento": documento, "motor_personas": motor_personas, "entidades": entidades}
