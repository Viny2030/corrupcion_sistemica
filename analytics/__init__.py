"""Módulos analíticos del Mapa de Transparencia, uno por capa metodológica:

- sna.py           Capa 1: redes complejas, cartelización, grafo bipartito/tripartito.
- finanzas.py       Capa 2: finanzas públicas, captura de mercado, ROI político.
- conductual.py     Capa 3: diagnóstico conductual y compliance.
- judicial_nlp.py   Capa 4: vaciamiento institucional y control judicial.
- entity_resolution.py  Transversal: identifica entidades reales duplicadas.
- scoring.py        Combina las 4 capas en un score de riesgo explicable (XAI).

Todas las funciones reciben datos reales (DataFrames/listas de dicts
provenientes de ingestion/ o de la base de datos) y no generan ni
requieren datos simulados.
"""
