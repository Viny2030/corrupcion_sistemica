# corrupcion_sistemica

Monitor independiente y autónomo de análisis de **corrupción sistémica**
sobre **datos reales** (no simulados): contrataciones públicas, finanzas
estatales, actividad legislativa, compliance corporativo y Poder Judicial,
siguiendo una arquitectura de 4 capas: SNA, Finanzas Públicas, Conductual/
Compliance y Vaciamiento Institucional.

**Aclaración de identidad, importante:** este repositorio ES el monitor
de Corrupción Sistémica — un desarrollo propio, standalone, que se
despliega y corre por su cuenta (pensado para Railway), con su propia API,
scheduler y base de datos. **NO es el "Mapa de Transparencia"**: ese es un
ecosistema/hub externo más amplio (con otros monitores — COMPRAR TGN,
MONITOR CONTRATOS, PODER JUDICIAL, etc.) al que este repo se integrará
más adelante como uno de sus monitores, consumiendo su API REST (ver más
abajo), sin que este servicio dependa de ese hub para funcionar.

## Estructura

```
corrupcion_sistemica/
├── .github/workflows/scrapers_diarios.yml   Cron diario (GitHub Actions)
├── api/main.py                   API REST autónoma (FastAPI) + scheduler interno
├── Dockerfile / railway.json     Despliegue en Railway
├── config/settings.py          Endpoints reales y configuración de BD
├── db/schema.sql                Esquema PostgreSQL del grafo multipartito
├── ingestion/                   Conectores a fuentes públicas reales
│   ├── cpi_transparency.py      Transparency International — CPI
│   ├── wgi_worldbank.py         World Bank — Worldwide Governance Indicators
│   ├── compras_publicas_ar.py   datos.gob.ar — Compr.ar / Contrat.ar
│   ├── hcdn_votaciones.py       Cámara de Diputados — votaciones (SPA, Playwright)
│   ├── senado_votaciones.py     Senado — votaciones (SPA, Playwright)
│   ├── bora_boletin.py          Boletín Oficial (SPA, Playwright)
│   ├── judicial_saij.py         SAIJ — jurisprudencia (SPA, Playwright)
│   ├── meaci_compliance.py      Carga de auditorías de compliance (export real)
│   └── _browser.py              Helper Playwright compartido por los scrapers SPA
├── scripts/inspeccionar_selectores.py   Vuelca el HTML real renderizado para calibrar selectores
├── analytics/                   Los 4 módulos analíticos + scoring/XAI
├── pipeline.py                  Orquestador: ingesta -> análisis -> dashboard/data.json
├── dashboard/index.html         Dashboard interactivo (autocontenido)
├── tests/test_analytics.py      Verificación de fórmulas (HHI, betweenness, etc.)
├── tests/test_scrapers.py       Parseo de BORA/HCDN/Senado/SAIJ contra fixtures locales
├── tests/fixtures/*.html         HTML de prueba (no son descargas reales) para los tests de scrapers
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
playwright install chromium   # scrapers SPA: BORA/HCDN/Senado/SAIJ
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

# Levantar la API autónoma en local
uvicorn api.main:app --reload
```

```bash
pytest -q   # corre las verificaciones de fórmulas + parsers de scrapers
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
- Literatura académica de referencia: Pohlmann et al. 2024 (Springer, DOI 10.1007/978-3-658-43579-0); Jackson 2025 (Public Integrity); Steel 2026 (SSRN 6293758); Ware et al. 2011 (Handbook of Global Research and Practice in Corruption); World Bank GIUP/eMBeD — Behavioral Insights to Fight Corruption; Klitgaard 2003.

## Scrapers (BORA / HCDN / Senado / SAIJ) — SPA + Playwright

Verificación real hecha sobre los sitios: pedir el HTML de
`boletinoficial.gob.ar`, `votaciones.hcdn.gob.ar`, `senado.gob.ar` y
`saij.gob.ar` con un cliente HTTP simple devuelve la página vacía o solo
el "shell" de la aplicación — los cuatro sitios son SPAs que arman el
contenido con JavaScript en el navegador, no server-rendered HTML. Por eso
estos 4 conectores no pueden funcionar con `requests` + BeautifulSoup
solos y ahora:

1. Usan **Playwright** (`ingestion/_browser.py`) para abrir un Chromium
   headless real, ejecutar el JS de la página y (en BORA/SAIJ) completar
   el formulario de búsqueda de verdad (`get_by_role`/`get_by_placeholder`,
   más estable ante cambios de CSS que clases hardcodeadas).
2. El parseo (`normalize()`) prueba primero selectores CSS específicos y,
   si no encuentran nada, cae a una **heurística genérica** (enlaces a
   `/detalleAviso/`, tablas con columnas reconocibles, fechas `DD/MM/AAAA`)
   para no quedar 100% atado a una clase que puede cambiar.

**Instalación:** `pip install -r requirements.txt && playwright install chromium`
(en Docker/Railway ya está en el `Dockerfile` con `--with-deps`).

**Tests (`tests/test_scrapers.py`):** no abren navegador ni pegan contra
la red. Alimentan `normalize()` con fixtures locales en `tests/fixtures/*.html`
— HTML mínimo escrito a mano que reproduce la forma esperada del DOM ya
renderizado (una versión "con las clases que se asumieron" y otra
"genérica sin esas clases", para probar ambos caminos del parser). Corré
`pytest -q`.

**Importante — calibración pendiente contra los sitios reales:** los
selectores CSS específicos en `bora_boletin.py` y `judicial_saij.py` son
un primer intento razonable, no una verificación contra el DOM real.
Antes de usar en producción, corré:

```bash
playwright install chromium
python scripts/inspeccionar_selectores.py bora
python scripts/inspeccionar_selectores.py hcdn --anio 2025
python scripts/inspeccionar_selectores.py senado --anio 2025
python scripts/inspeccionar_selectores.py saij --texto "corrupción"
```

Esto guarda el HTML real ya renderizado en `scripts/_dump_<sitio>.html`.
Si los selectores no matchean, el fallback genérico debería igual traer
algo; ajustá `_extraer_con_selectores_conocidos` en cada conector con lo
que veas en el dump.

## Cron diario de los scrapers — GitHub Actions

El scraping/ingesta diaria **no depende de Railway**: corre como workflow
de GitHub Actions en `.github/workflows/scrapers_diarios.yml`.

- **Cuándo corre**: todos los días a las 09:00 UTC (06:00 ART) — ajustable
  editando el `cron:` del workflow — y también a demanda desde la pestaña
  **Actions → Scrapers diarios → Run workflow**.
- **Qué hace**: instala dependencias + Chromium de Playwright, corre
  `python pipeline.py` (ingesta real de CPI/WGI y, si hay CSV configurados,
  Capa 1/2 de contrataciones), corre `pytest -q` (fórmulas + parsers de
  scrapers) y, si `dashboard/data.json` cambió, lo commitea al repo.
- **Secrets a configurar** (Settings → Secrets and variables → Actions),
  solo si el pipeline necesita conectarse a Postgres: `PG_HOST`, `PG_PORT`,
  `PG_DB`, `PG_USER`, `PG_PASSWORD`. Si no los configurás, el pipeline
  sigue funcionando igual para CPI/WGI (usa los valores por defecto de
  `config/settings.py`).
- **Permisos**: el workflow ya declara `permissions: contents: write` para
  poder pushear el `data.json` actualizado con el token automático de
  GitHub Actions (no hace falta crear un PAT).

Es independiente del servicio en Railway: podés usar los dos (Railway para
la API que consultará el hub Mapa de Transparencia cuando se integre este
monitor, GitHub Actions para mantener `dashboard/data.json` fresco) o solo
uno de los dos.

## Despliegue en Railway (servicio autónomo)

El proyecto corre como servicio Docker independiente. En Railway:

1. **Nuevo proyecto → Deploy from repo**, apuntando a este repositorio.
   Railway detecta `Dockerfile`/`railway.json` automáticamente.
2. **Variables de entorno** (Settings → Variables): `PG_HOST`, `PG_PORT`,
   `PG_DB`, `PG_USER`, `PG_PASSWORD` (o conectá el plugin de PostgreSQL de
   Railway y usá sus valores), `PIPELINE_INTERVAL_HOURS` (default 24),
   `ALLOWED_ORIGINS` (dominios que van a consumir la API, separados por
   coma), `DESHABILITAR_SCHEDULER=true` si preferís que el único cron
   diario sea el de GitHub Actions.
3. **Base de datos**: agregá el plugin Postgres de Railway y corré
   `db/schema.sql` una vez (`railway run psql $DATABASE_URL -f db/schema.sql`).
4. **Healthcheck**: ya configurado en `railway.json` (`/health`).
5. **(Opcional) Cron nativo de Railway en vez de GitHub Actions**: si
   preferís no depender de GitHub Actions, creá un segundo servicio en el
   mismo proyecto de Railway, tipo "Cron Job", mismo repo, comando
   `python pipeline.py` y el schedule que necesites (ej. `0 6 * * *`). Con
   `DESHABILITAR_SCHEDULER=true` en el servicio web evitás correr el
   pipeline dos veces.

### Endpoints expuestos (para cuando este monitor se integre al hub Mapa de Transparencia)

| Método | Ruta | Uso |
|---|---|---|
| GET | `/health` | Healthcheck (Railway) |
| GET | `/indicadores/macro` | CPI / WGI reales (filtrable por `pais_iso3`, `indicador`) |
| GET | `/procurement/{bloque}` | co_presentismo, asimetria_victorias, hhi_por_organismo, low_balling |
| GET | `/scoring/reglas` | Reglas de scoring vigentes (transparencia del modelo) |
| POST | `/scoring/evaluar` | Score + audit card para una fila de indicadores real |
| POST | `/pipeline/ejecutar` | Dispara una corrida manual (acepta CSV reales por multipart) |

## Limitaciones y próximos pasos

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
- **Integración con el hub Mapa de Transparencia**: este repo expone la
  API lista para ser consumida, pero la integración en sí (autenticación
  entre servicios, formato exacto que espera el hub, etc.) queda pendiente
  hasta que ese ecosistema esté definido.
