"""Tests de los scrapers (BORA, HCDN, Senado, SAIJ).

Importante: estos conectores dependen de Playwright para OBTENER el HTML
(fetch), porque los 4 sitios resultaron ser SPAs renderizadas por JS
(verificado con un cliente HTTP simple: devuelven la página vacía). Estos
tests NO abren un navegador ni pegan contra la red: prueban únicamente la
lógica de PARSEO (`normalize()` y sus helpers), alimentándola con fixtures
locales en `tests/fixtures/` que reproducen la forma esperada del DOM ya
renderizado. Así se puede verificar el parser sin depender de Internet ni
de que el sitio esté arriba, y sin fabricar ningún dato de corrupción real.

Antes de producción: correr `python scripts/inspeccionar_selectores.py <sitio>`
contra el sitio real y comparar su estructura con estas fixtures; ajustar
selectores en `ingestion/*.py` si difieren.
"""

from pathlib import Path

import pytest

from ingestion.bora_boletin import ConectorBORA
from ingestion.hcdn_votaciones import ConectorHCDNVotaciones
from ingestion.senado_votaciones import ConectorSenadoVotaciones
from ingestion.judicial_saij import ConectorSAIJ

DIR_FIXTURES = Path(__file__).parent / "fixtures"


def _leer_fixture(nombre: str) -> str:
    return (DIR_FIXTURES / nombre).read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# BORA
# ---------------------------------------------------------------------------

def test_bora_parsea_con_selectores_conocidos():
    html = _leer_fixture("bora_con_clases.html")
    registros = ConectorBORA().normalize(html)
    assert len(registros) == 2
    assert registros[0]["titulo"] == "Adjudicación Licitación Pública 45/2026"
    assert registros[0]["fecha"] == "05/08/2026"
    assert registros[0]["organismo"] == "Ministerio de Obras Públicas"
    assert registros[0]["url"] == "/detalleAviso/999888"


def test_bora_cae_a_heuristica_generica_si_no_hay_clases_conocidas():
    html = _leer_fixture("bora_generico.html")
    registros = ConectorBORA().normalize(html)
    assert len(registros) == 1
    assert registros[0]["url"] == "/detalleAviso/111222"
    assert registros[0]["fecha"] == "03/08/2026"


# ---------------------------------------------------------------------------
# HCDN
# ---------------------------------------------------------------------------

def test_hcdn_cae_a_tabla_renderizada_sin_links_de_descarga():
    html = _leer_fixture("hcdn_tabla.html")
    registros = ConectorHCDNVotaciones().normalize(html)
    assert len(registros) == 2
    assert registros[0]["legislador"] == "Juan Pérez"
    assert registros[0]["voto"] == "AFIRMATIVO"
    assert registros[1]["legislador"] == "Ana Gómez"
    assert registros[1]["voto"] == "NEGATIVO"
    assert all(r["camara"] == "DIPUTADOS" for r in registros)


def test_hcdn_sin_tabla_ni_links_devuelve_vacio():
    registros = ConectorHCDNVotaciones().normalize("<html><body>Sin resultados</body></html>")
    assert registros == []


# ---------------------------------------------------------------------------
# Senado
# ---------------------------------------------------------------------------

def test_senado_parsea_tabla_generica():
    html = _leer_fixture("senado_tabla.html")
    registros = ConectorSenadoVotaciones().normalize(html)
    assert len(registros) == 1
    assert registros[0]["camara"] == "SENADORES"
    assert registros[0]["expediente"] == "S-45/26"
    assert registros[0]["resultado"] == "APROBADO"


def test_senado_sin_tabla_devuelve_vacio():
    registros = ConectorSenadoVotaciones().normalize("<html><body>Sin resultados</body></html>")
    assert registros == []


# ---------------------------------------------------------------------------
# SAIJ
# ---------------------------------------------------------------------------

def test_saij_parsea_con_selectores_conocidos():
    html = _leer_fixture("saij_con_clases.html")
    registros = ConectorSAIJ().normalize(html)
    assert len(registros) == 1
    assert "Corrupción Administrativa" in registros[0]["caratula"]
    assert registros[0]["fuero"] == "Contencioso Administrativo Federal"
    assert "prisión efectiva" in registros[0]["texto_fallo"]


def test_saij_cae_a_heuristica_generica():
    html = _leer_fixture("saij_generico.html")
    registros = ConectorSAIJ().normalize(html)
    assert len(registros) == 1
    assert "Malversación" in registros[0]["caratula"]
    assert registros[0]["fecha_resolucion"] == "10/06/2026"


# ---------------------------------------------------------------------------
# _browser.py — error explícito si Playwright no está instalado
# ---------------------------------------------------------------------------

def test_obtener_html_renderizado_falla_explicito_sin_playwright(monkeypatch):
    import builtins

    from ingestion import _browser

    real_import = builtins.__import__

    def import_bloqueando_playwright(nombre, *args, **kwargs):
        if nombre.startswith("playwright"):
            raise ImportError("simulado: playwright no instalado")
        return real_import(nombre, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", import_bloqueando_playwright)

    with pytest.raises(RuntimeError, match="Playwright"):
        _browser.obtener_html_renderizado("https://example.com")
