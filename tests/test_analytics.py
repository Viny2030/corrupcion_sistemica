"""Tests de verificación de fórmulas (NO simulan corrupción: usan ejemplos
mínimos de laboratorio con respuesta conocida, solo para probar que cada
indicador matemático está implementado correctamente antes de aplicarlo
sobre datos reales)."""

import networkx as nx
import pandas as pd

from analytics import finanzas, sna, scoring


def test_hhi_monopolio_da_10000():
    licitaciones = pd.DataFrame(
        {"organismo": ["A", "A"], "proveedor": ["X", "X"], "monto_adjudicado": [100, 200]}
    )
    resultado = finanzas.hhi_por_organismo(licitaciones)
    assert resultado.iloc[0]["hhi"] == 10000.0
    assert resultado.iloc[0]["alta_concentracion"] == True  # noqa: E712 — viene como np.bool_, no bool


def test_hhi_competencia_perfecta_dos_iguales_da_5000():
    licitaciones = pd.DataFrame(
        {"organismo": ["A", "A"], "proveedor": ["X", "Y"], "monto_adjudicado": [100, 100]}
    )
    resultado = finanzas.hhi_por_organismo(licitaciones)
    assert resultado.iloc[0]["hhi"] == 5000.0


def test_co_presentismo_cuenta_pares_correctamente():
    ofertas = pd.DataFrame(
        {
            "licitacion_id": ["L1", "L1", "L2", "L2", "L2"],
            "empresa_id": ["X", "Y", "X", "Y", "Z"],
        }
    )
    matriz = sna.matriz_co_presentismo(ofertas)
    par_xy = matriz[(matriz.empresa_a.isin(["X", "Y"])) & (matriz.empresa_b.isin(["X", "Y"]))]
    assert par_xy.iloc[0]["co_presentismo"] == 2


def test_betweenness_centralidad_nodo_puente():
    # Grafo en línea A-B-C: B es el único paso obligado entre A y C.
    G = nx.Graph()
    G.add_edge("A", "B", weight=1.0)
    G.add_edge("B", "C", weight=1.0)
    resultado = sna.centralidad_intermediacion(G)
    top = resultado.iloc[0]
    assert top["nodo_id"] == "B"
    assert top["betweenness"] > 0


def test_low_balling_index_detecta_sobrecosto():
    licitaciones = pd.DataFrame(
        {
            "licitacion_id": ["L1"],
            "organismo": ["A"],
            "monto_adjudicado": [1000.0],
        }
    )
    adendas = pd.DataFrame(
        {"licitacion_id": ["L1"], "monto_original": [1000.0], "monto_nuevo": [1500.0]}
    )
    resultado = finanzas.low_balling_index(licitaciones, adendas)
    assert resultado.iloc[0]["low_balling_ratio"] == 0.5


def test_scoring_suma_reglas_activadas():
    fila = pd.Series({"alta_concentracion": True, "low_balling_ratio": 0.5})
    resultado = scoring.calcular_score(fila)
    assert "HHI_ELEVADO" in resultado["desglose"]
    assert "ADENDAS_REPETIDAS" in resultado["desglose"]
    assert resultado["score"] == resultado["desglose"]["HHI_ELEVADO"] + resultado["desglose"]["ADENDAS_REPETIDAS"]
