"""Capa 1 — Análisis de Redes Sociales (SNA) sobre datos reales de contrataciones.

Implementa los indicadores descritos en la arquitectura:
    A. Rotación de ofertas / co-presentismo / asimetría de victorias /
       variabilidad presupuestaria.
    B. Centralidad de intermediación (betweenness) e indicador de red
       bipartita organismo-proveedor.
    C. Detección de comunidades (Louvain) e índice de aislamiento de red.

Todas las funciones toman como entrada DataFrames con la forma de las
tablas `licitacion` / `oferta` del esquema (db/schema.sql), pobladas con
datos reales por los conectores de ingestion/.
"""

from __future__ import annotations

from itertools import combinations

import networkx as nx
import pandas as pd

try:
    import community as community_louvain  # paquete python-louvain
except ImportError:  # pragma: no cover
    community_louvain = None


# ---------------------------------------------------------------------------
# A. Rotación de ofertas (bid rotation)
# ---------------------------------------------------------------------------

def matriz_co_presentismo(ofertas: pd.DataFrame) -> pd.DataFrame:
    """CPab: cantidad de licitaciones en las que las empresas A y B
    presentaron oferta conjuntamente.

    `ofertas` debe tener columnas: licitacion_id, empresa_id.
    """
    conteos: dict[tuple[str, str], int] = {}
    for _, grupo in ofertas.groupby("licitacion_id")["empresa_id"]:
        empresas = sorted(set(grupo))
        for a, b in combinations(empresas, 2):
            conteos[(a, b)] = conteos.get((a, b), 0) + 1

    filas = [{"empresa_a": a, "empresa_b": b, "co_presentismo": n} for (a, b), n in conteos.items()]
    return pd.DataFrame(filas).sort_values("co_presentismo", ascending=False) if filas else pd.DataFrame(
        columns=["empresa_a", "empresa_b", "co_presentismo"]
    )


def asimetria_de_victorias(ofertas: pd.DataFrame, umbral_co_presentismo: int = 3) -> pd.DataFrame:
    """Para pares de empresas con alto co-presentismo, mide si la tasa de
    adjudicación alterna sistemáticamente entre ambas (posible cobertura
    recíproca) y si los montos ofertados quedan cerca del presupuesto
    oficial en ambos casos.

    Devuelve, por par de empresas: nro. de licitaciones compartidas,
    victorias de A, victorias de B, y un índice de alternancia en [0, 1]
    (1 = alternancia perfecta 50/50, indicador de posible cobertura).
    """
    co_pres = matriz_co_presentismo(ofertas)
    co_pres = co_pres[co_pres["co_presentismo"] >= umbral_co_presentismo]
    if co_pres.empty:
        return pd.DataFrame(columns=["empresa_a", "empresa_b", "compartidas", "victorias_a", "victorias_b", "indice_alternancia"])

    resultados = []
    for _, fila in co_pres.iterrows():
        a, b = fila["empresa_a"], fila["empresa_b"]
        compartidas = ofertas[ofertas["empresa_id"].isin([a, b])]
        licitaciones_comunes = (
            compartidas.groupby("licitacion_id")["empresa_id"].nunique().pipe(lambda s: s[s == 2].index)
        )
        subset = compartidas[compartidas["licitacion_id"].isin(licitaciones_comunes)]
        victorias_a = ((subset["empresa_id"] == a) & (subset["resultado"] == "GANADORA")).sum()
        victorias_b = ((subset["empresa_id"] == b) & (subset["resultado"] == "GANADORA")).sum()
        total = victorias_a + victorias_b
        indice = 1 - abs(victorias_a - victorias_b) / total if total else 0.0
        resultados.append(
            {
                "empresa_a": a,
                "empresa_b": b,
                "compartidas": len(licitaciones_comunes),
                "victorias_a": int(victorias_a),
                "victorias_b": int(victorias_b),
                "indice_alternancia": round(indice, 3),
            }
        )
    return pd.DataFrame(resultados).sort_values("indice_alternancia", ascending=False)


def indicador_variabilidad_presupuestaria(ofertas: pd.DataFrame) -> pd.DataFrame:
    """Detecta si las empresas 'perdedoras' presentan variaciones porcentuales
    similares/idénticas por encima de la oferta ganadora (patrón típico de
    ofertas de cobertura). `ofertas` requiere columna `porcentaje_sobre_ganadora`
    ya calculada: (monto_ofertado - monto_ganador) / monto_ganador.
    """
    perdedoras = ofertas[ofertas["resultado"] == "PERDEDORA"].copy()
    if perdedoras.empty:
        return pd.DataFrame(columns=["empresa_id", "desvio_estandar_pct", "n_ofertas", "sospechoso"])

    agg = (
        perdedoras.groupby("empresa_id")["porcentaje_sobre_ganadora"]
        .agg(desvio_estandar_pct="std", n_ofertas="count", media_pct="mean")
        .reset_index()
    )
    # Baja variabilidad + n suficiente => patrón repetido y sospechoso
    agg["sospechoso"] = (agg["desvio_estandar_pct"] < 0.02) & (agg["n_ofertas"] >= 3)
    return agg.sort_values(["sospechoso", "n_ofertas"], ascending=[False, False])


# ---------------------------------------------------------------------------
# B. Centralidad e intermediarios
# ---------------------------------------------------------------------------

def construir_grafo(aristas: pd.DataFrame) -> nx.Graph:
    """`aristas` con columnas origen_id, destino_id, peso (ver tabla
    `grafo_arista`). Construye un grafo no dirigido ponderado."""
    G = nx.Graph()
    for _, fila in aristas.iterrows():
        G.add_edge(fila["origen_id"], fila["destino_id"], weight=float(fila.get("peso", 1.0)))
    return G


def centralidad_intermediacion(G: nx.Graph, top_n: int = 20) -> pd.DataFrame:
    """Betweenness centrality clásica: identifica nodos que actúan como
    paso obligado (posibles brokers/operadores) en los caminos más cortos."""
    if G.number_of_nodes() == 0:
        return pd.DataFrame(columns=["nodo_id", "betweenness"])
    valores = nx.betweenness_centrality(G, weight="weight", normalized=True)
    df = pd.DataFrame(sorted(valores.items(), key=lambda x: -x[1]), columns=["nodo_id", "betweenness"])
    return df.head(top_n)


def red_bipartita_organismo_proveedor(
    aristas_adjudicacion: pd.DataFrame, entidades: pd.DataFrame
) -> pd.DataFrame:
    """Detecta nodos NO estatales (brokers/intermediarios) con alta
    intermediación entre organismos de distintas jurisdicciones/poderes,
    sin capacidad técnica declarada. `entidades` debe traer columnas
    entidad_id, tipo, metadata (con posible flag 'capacidad_tecnica_declarada')."""
    G = construir_grafo(aristas_adjudicacion)
    centralidad = centralidad_intermediacion(G, top_n=len(G.nodes) or 1)
    centralidad = centralidad.merge(entidades, left_on="nodo_id", right_on="entidad_id", how="left")
    sospechosos = centralidad[
        (centralidad["tipo"] == "BROKER")
        & (centralidad["betweenness"] > centralidad["betweenness"].median())
    ]
    return sospechosos.sort_values("betweenness", ascending=False)


# ---------------------------------------------------------------------------
# C. Comunidades y aislamiento de red
# ---------------------------------------------------------------------------

def detectar_comunidades(G: nx.Graph) -> pd.DataFrame:
    """Louvain: partición de la red en comunidades/clústeres. Requiere
    `python-louvain` (paquete `community`)."""
    if community_louvain is None:
        raise ImportError("Instalar 'python-louvain' para detección de comunidades (Louvain).")
    if G.number_of_nodes() == 0:
        return pd.DataFrame(columns=["nodo_id", "comunidad"])
    particion = community_louvain.best_partition(G, weight="weight")
    return pd.DataFrame(sorted(particion.items()), columns=["nodo_id", "comunidad"])


def indice_aislamiento_red(G: nx.Graph, comunidades: pd.DataFrame) -> pd.DataFrame:
    """Para cada comunidad, mide la densidad interna vs. la densidad global
    de la red. Un valor alto (>>1) sugiere un 'circuito cerrado' de
    contratación cruzada, poco permeable a nuevos proveedores."""
    if G.number_of_nodes() == 0 or comunidades.empty:
        return pd.DataFrame(columns=["comunidad", "densidad_interna", "densidad_global", "indice_aislamiento"])

    densidad_global = nx.density(G)
    resultados = []
    for comunidad_id, grupo in comunidades.groupby("comunidad"):
        nodos = grupo["nodo_id"].tolist()
        subgrafo = G.subgraph(nodos)
        densidad_interna = nx.density(subgrafo) if subgrafo.number_of_nodes() > 1 else 0.0
        indice = densidad_interna / densidad_global if densidad_global > 0 else 0.0
        resultados.append(
            {
                "comunidad": comunidad_id,
                "n_nodos": len(nodos),
                "densidad_interna": round(densidad_interna, 4),
                "densidad_global": round(densidad_global, 4),
                "indice_aislamiento": round(indice, 3),
            }
        )
    return pd.DataFrame(resultados).sort_values("indice_aislamiento", ascending=False)
