"""Tests del motor de NLP sobre el Boletín Oficial. Texto de ejemplo
mínimo (no es un aviso real descargado, es un caso de laboratorio con
todos los formatos esperados) para verificar cada extractor por
separado, igual filosofía que tests/test_analytics.py."""
from services import nlp_service

TEXTO_EJEMPLO = """
Decreto 123/2026. VISTO el Expediente EX-2024-12345678- -APN-DGD#MEC, y
CONSIDERANDO que la empresa CONSTRUCTORA DEL SUR S.A. (CUIT
30-71659554-9), representada por el Sr. Juan Carlos Perez, resultó
adjudicataria del contrato por un monto de $ 125.000.000,50 otorgado por
el MINISTERIO DE ECONOMIA en el marco de la licitación pública
gestionada por la SECRETARIA DE OBRAS PUBLICAS. La empresa LOGISTICA
NORTE S.R.L. actuó como subcontratista, con CUIT 30-12345678-1, y la
ANSES verificó el cumplimiento fiscal.
"""


def test_extraer_cuit_encuentra_los_dos_cuit_reales():
    cuits = nlp_service.extraer_cuit(TEXTO_EJEMPLO)
    assert "30-71659554-9" in cuits
    assert "30-12345678-1" in cuits
    assert len(cuits) == 2


def test_extraer_montos_encuentra_el_monto():
    montos = nlp_service.extraer_montos(TEXTO_EJEMPLO)
    assert any("125.000.000" in m for m in montos)


def test_extraer_expedientes_encuentra_el_expediente_gde():
    expedientes = nlp_service.extraer_expedientes(TEXTO_EJEMPLO)
    assert len(expedientes) == 1
    assert expedientes[0].startswith("EX-2024-12345678")


def test_extraer_empresas_encuentra_las_dos_empresas():
    empresas = nlp_service.extraer_empresas(TEXTO_EJEMPLO)
    assert any("CONSTRUCTORA DEL SUR" in e for e in empresas)
    assert any("LOGISTICA NORTE" in e for e in empresas)


def test_extraer_organismos_encuentra_ministerio_secretaria_y_sigla():
    organismos = nlp_service.extraer_organismos(TEXTO_EJEMPLO)
    assert any("MINISTERIO DE ECONOMIA" in o for o in organismos)
    assert any("SECRETARIA DE OBRAS PUBLICAS" in o for o in organismos)
    assert "ANSES" in organismos


def test_extraer_personas_encuentra_el_nombre_con_titulo():
    personas, motor = nlp_service.extraer_personas(TEXTO_EJEMPLO)
    assert any("Juan Carlos Perez" in p for p in personas)
    assert motor in ("spacy_es_core_news_sm", "heuristico_titulos")


def test_extraer_entidades_devuelve_los_6_tipos():
    resultado = nlp_service.extraer_entidades(TEXTO_EJEMPLO, documento="Decreto 123/2026")
    assert resultado["documento"] == "Decreto 123/2026"
    tipos = {e["tipo"] for e in resultado["entidades"]}
    assert tipos == {"persona", "empresa", "organismo", "cuit", "monto", "expediente"}


def test_extraer_entidades_con_texto_vacio_no_rompe():
    resultado = nlp_service.extraer_entidades("")
    assert resultado["entidades"] == []
