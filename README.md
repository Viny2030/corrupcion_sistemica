# Mapa de Transparencia — Módulo de Corrupción Sistémica (Monitor 12)

Motor de correlación sobre **datos reales** (no simulados) para detectar
patrones de corrupción sistémica en contrataciones públicas, finanzas
estatales, actividad legislativa, compliance corporativo y Poder Judicial,
siguiendo la arquitectura de 4 capas: SNA, Finanzas Públicas, Conductual/
Compliance y Vaciamiento Institucional.

**Este repositorio es un desarrollo independiente y autónomo**: se
despliega y corre por su cuenta (pensado para Railway), con su propia API,
scheduler y base de datos. Más adelante se integra como **Monitor 12**
dentro del ecosistema "Mapa de Transparencia" (los otros 11 módulos —
COMPRAR TGN, MONITOR CONTRATOS, PODER JUDICIAL, etc. — lo consumen vía su
API REST, sin que este servicio dependa de ellos para funcionar).

## Estructura

```
mapa_transparencia/
├── api/main.py                   API REST autónoma (FastAPI) + scheduler interno
├── Dockerfile / railway.json     Despliegue en Railway
├── config/settings.py          Endpoints reales y configuración de BD
├── db/schema.sql                Esquema PostgreSQL del grafo multipartito
├── ingestion/                   Conectores a fuentes públicas reales
│   ├── cpi_transparency.py      Transparency International — CPI
│   ├── wgi_worldbank.py         World Bank — Worldwide Governance Indicators
│   ├── compras_publicas_ar.py   datos.gob.ar — Compr.ar / Contrat.ar
│   ├── hcdn_votaciones.py       Cámara de Diputados — votaciones
│   ├── senado_votaciones.py     Senado — votaciones
│   ├── bora_boletin.py          Boletín Oficial (scraper)
│   ├── judicial_saij.py         SAIJ — jurisprudencia
│   └── meaci_compliance.py      Carga de auditorías de compliance (export real)
├── analytics/                   Los 4 módulos analíticos + scoring/XAI
├── pipeline.py                  Orquestador: ingesta -> análisis -> dashboard/data.json
├── dashboard/index.html         Dashboard interactivo (autocontenido)
├── tests/test_analytics.py      Verificación de fórmulas (HHI, betweenness, etc.)
└── docker-compose.yml           Postgres + PostGIS para levantar el esquema
```

## Principio de diseño: nada de datos simulados

Cada conector en `ingestion/` trae datos reales desde una fuente pública o
falla explícitamente (lista vacía / excepción) si la fuente no responde.
Ningún módulo analítico genera registros ficticios para "rellenar" una
demo. El `dashboard/data.json` de ejemplo incluido solo contiene:

- Valores reales de **CPI** (Transparency International) y **WGI Control
  of Corruption** (Banco Mundial) para Argentina, verificados manualmente.
- Los paneles de contrataciones (SNA, HHI, low-balling) figuran como
  **"esperando datos reales"** hasta que corras el pipeline con tus
  propios CSV de licitaciones/ofertas/adendas.

## Instalación

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # editar credenciales de Postgres
docker compose up -d   # levanta Postgres+PostGIS con el esquema ya aplicado
```

## Uso

```bash
# Solo indicadores macro reales (CPI/WGI) -> dashboard/data.json
python pipeline.py

# Con tus propios datos reales de contrataciones
python pipeline.py --ofertas ofertas.csv --licitaciones licitaciones.csv --adendas adendas.csv

# Abrir el dashboard
open dashboard/index.html   # o servirlo: python -m http.server --directory dashboard
```

```bash
pytest -q   # corre las verificaciones de fórmulas (analytics/)
```

## Indicadores implementados por capa

**Capa 1 (SNA)** — `analytics/sna.py`, `analytics/entity_resolution.py`
- Matriz de co-presentismo (bid rotation)
- Índice de alternancia de victorias
- Indicador de variabilidad presupuestaria entre ofertas perdedoras
- Centralidad de intermediación (betweenness) y red bipartita organismo-broker
- Detección de comunidades (Louvain) e índice de aislamiento de red
- Resolución de entidades (fuzzy matching: domicilio, email, directorio)

**Capa 2 (Finanzas Públicas)** — `analytics/finanzas.py`
- TGN Bias (priorización de pagos)
- HHI de concentración presupuestaria por organismo
- Low-balling index (desvío adjudicado vs. ejecutado vía adendas)
- ROI político (aportes de campaña vs. contrataciones posteriores)

**Capa 3 (Conductual/Compliance)** — `analytics/conductual.py`
- Sludge Index (fricción burocrática anómala)
- MEACI Audit Score (compliance real vs. "de papel")
- Cruce de percepción ciudadana de fricción (report cards)

**Capa 4 (Judicial)** — `analytics/judicial_nlp.py`
- Tasa de extinción por prescripción
- Sesgo de sanción (clasificación de severidad textual de fallos)
- Matriz voto-contrato (votos legislativos vs. contrataciones a empresas vinculadas)

**Scoring/XAI** — `analytics/scoring.py`
- Score de riesgo 0-100 por licitación/empresa con "Audit Card" (desglose
  transparente de qué reglas y sobre qué dato real se activaron).

## Fuentes reales utilizadas

- Transparency International — Corruption Perceptions Index: https://www.transparency.org/en/cpi/
  - Argentina 2025: 36/100 (puesto 104/182); 2024: 37/100. [Buenos Aires Herald](https://buenosairesherald.com/business/argentina-reaches-worst-score-in-corruption-perceptions-index-since-2019)
- World Bank — Worldwide Governance Indicators: https://www.worldbank.org/en/publication/worldwide-governance-indicators
  - Argentina, Control of Corruption (Estimate): 2023 = -0.36; 2022 = -0.45. [data.worldbank.org](https://data.worldbank.org/indicator/CC.EST?locations=AR)
- Datos Argentina (CKAN) — Contrataciones públicas: https://datos.gob.ar/dataset/jgm-sistema-contrataciones-electronicas
- HCDN — Datos abiertos / votaciones: https://datos.hcdn.gob.ar / https://votaciones.hcdn.gob.ar
- Senado — Votaciones: https://www.senado.gob.ar/parlamentario/parlamentaria/votaciones
- Boletín Oficial (BORA): https://www.boletinoficial.gob.ar
- SAIJ: http://www.saij.gob.ar
- Literatura académica de referencia (ver documento original del proyecto): Pohlmann et al. 2024 (Springer, DOI 10.1007/978-3-658-43579-0); Jackson 2025 (Public Integrity); Steel 2026 (SSRN 6293758); Ware et al. 2011 (Handbook of Global Research and Practice in Corruption); World Bank GIUP/eMBeD — Behavioral Insights to Fight Corruption; Klitgaard 2003.

## Despliegue en Railway (servicio autónomo)

El proyecto corre como servicio Docker independiente. En Railway:

1. **Nuevo proyecto → Deploy from repo**, apuntando a este repositorio.
   Railway detecta `Dockerfile`/`railway.json` automáticamente.
2. **Variables de entorno** (Settings → Variables): `PG_HOST`, `PG_PORT`,
   `PG_DB`, `PG_USER`, `PG_PASSWORD` (o conectá el plugin de PostgreSQL de
   Railway y usá sus valores), `PIPELINE_INTERVAL_HOURS` (default 24),
   `ALLOWED_ORIGINS` (dominios del hub central que van a consumir la API,
   separados por coma), `DESHABILITAR_SCHEDULER=true` si preferís usar
   solo el Cron Job nativo en vez del scheduler interno.
3. **Base de datos**: agregá el plugin Postgres de Railway y corré
   `db/schema.sql` una vez (`railway run psql $DATABASE_URL -f db/schema.sql`).
4. **Healthcheck**: ya configurado en `railway.json` (`/health`).
5. **(Opcional) Cron Job separado**: si preferís que el pipeline corra
   fuera del proceso web, creá un segundo servicio en el mismo proyecto de
   Railway, tipo "Cron Job", mismo repo, comando `python pipeline.py` y el
   schedule que necesites (ej. `0 6 * * *`). Con `DESHABILITAR_SCHEDULER=true`
   en el servicio web evitás correr el pipeline dos veces.

### Endpoints expuestos (para el hub central del Mapa de Transparencia)

| Método | Ruta | Uso |
|---|---|---|
| GET | `/health` | Healthcheck (Railway) |
| GET | `/indicadores/macro` | CPI / WGI reales (filtrable por `pais_iso3`, `indicador`) |
| GET | `/procurement/{bloque}` | co_presentismo, asimetria_victorias, hhi_por_organismo, low_balling |
| GET | `/scoring/reglas` | Reglas de scoring vigentes (transparencia del modelo) |
| POST | `/scoring/evaluar` | Score + audit card para una fila de indicadores real |
| POST | `/pipeline/ejecutar` | Dispara una corrida manual (acepta CSV reales por multipart) |

## Limitaciones y próximos pasos

- **BORA, Senado y SAIJ no tienen API pública formal**: los conectores
  hacen scraping sobre el HTML actual del sitio; revisar los selectores
  CSS en `ingestion/bora_boletin.py`, `senado_votaciones.py` y
  `judicial_saij.py` si el sitio cambia de maquetación.
- **MEACI**: no existe un portal público unificado de auditorías de
  compliance; `ingestion/meaci_compliance.py` espera un export real
  (CSV/XLSX) provisto por el equipo de auditoría u organismo de control.
- **Motor de grafos (Neo4j) y orquestación (Airflow)**: el esquema y el
  pipeline están listos para alimentarlos (export a GraphML/JSON-LD
  desde `grafo_arista`), pero su despliegue no está incluido en esta
  primera versión — el foco fue el motor analítico sobre datos reales.
- **NLP judicial**: `analytics/judicial_nlp.py` usa una heurística léxica
  transparente y auditable como punto de partida; para producción se
  recomienda un modelo entrenado sobre un corpus real de fallos etiquetado.
