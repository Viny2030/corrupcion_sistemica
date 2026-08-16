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
├── api/
│   ├── main.py                   API REST autónoma (FastAPI) + scheduler interno + endpoints heredados
│   └── v1/                       /api/v1/* — superficie nueva organizada por recurso
│       ├── contratos.py          GET /api/v1/contratos, /contratos/{bloque}
│       ├── empresas.py           GET /api/v1/empresas, /empresas/{identificador}
│       ├── redes.py              GET /api/v1/redes, /redes/empresa/{identificador}
│       ├── patrones.py           GET /api/v1/patrones, /patrones/reglas
│       ├── riesgo.py             GET /riesgo/empresa/{id}, POST /riesgo/ircs
│       ├── documentos.py         POST /api/v1/documentos/procesar — NER sobre texto real (Boletín Oficial u otro)
│       └── alertas.py            GET /api/v1/alertas
├── schemas/                      Contratos Pydantic de entrada/salida de la API
├── models/                       Modelos de dominio interno (mirror de db/schema.sql, no ORM todavía)
├── services/                     Capa de servicios entre api/v1/ y analytics/
│   ├── concentration_service.py  Motor de concentración: HHI + Top3/Top5/por categoría/evolución temporal
│   ├── network_service.py        Motor de redes: degree/betweenness/closeness/PageRank/comunidad + network_score
│   ├── pattern_service.py        Motor de patrones: REGLA-001 a REGLA-008, explicables
│   ├── risk_service.py           Índice IRCS: combina concentración+redes+patrones+anomalías+opacidad+institucional
│   ├── nlp_service.py            NER híbrido (spaCy + regex) sobre texto real: personas/empresas/organismos/CUIT/montos/expedientes
│   └── data_store.py             Lectura del último dashboard/data.json
├── ml/                            Motor A — anomalías con ML no supervisado
│   ├── isolation_forest.py       Isolation Forest sobre monto/ofertas/duración/modificaciones
│   ├── clustering.py             Local Outlier Factor + DBSCAN
│   └── scoring.py                Combina los 3 modelos (0.4/0.4/0.2) en anomaly_score 0-100 + factores explicativos
├── database/                      Persistencia real en Postgres (además de dashboard/data.json)
│   ├── connection.py             Motor/sesión SQLAlchemy perezosos + verificar_conexion() (nunca rompe el pipeline)
│   ├── models.py                 ORM SQLAlchemy 2.0 de las 15 tablas de db/schema.sql
│   └── repositories.py           Upserts idempotentes (entidad/licitación/indicador) + historial (aristas/scores)
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
├── analytics/                   Los 4 módulos analíticos + scoring/XAI (capas originales)
├── pipeline.py                  Orquestador: ingesta -> análisis (analytics/ + services/) -> dashboard/data.json
├── dashboard/index.html         Dashboard interactivo (autocontenido)
├── tests/test_analytics.py      Verificación de fórmulas (HHI, betweenness, etc.)
├── tests/test_pattern_service.py Verificación de las 8 reglas del motor de patrones
├── tests/test_risk_service.py   Verificación del cálculo del IRCS
├── tests/test_api_v1.py         Contrato HTTP de /api/v1/*
├── tests/test_ml_scoring.py     Verificación del Motor A (Isolation Forest/LOF/DBSCAN + fallback heurístico)
├── tests/test_nlp_service.py    Verificación del NER híbrido (spaCy + regex) sobre texto real
├── tests/test_database.py       Verificación del ORM/repositorios contra un Postgres real con db/schema.sql aplicado
├── tests/test_scrapers.py       Parseo de BORA/HCDN/Senado/SAIJ contra fixtures locales
├── tests/fixtures/*.html         HTML de prueba (no son descargas reales) para los tests de scrapers
└── docker-compose.yml           Postgres + PostGIS para levantar el esquema
```

`graph/` (exportación a Neo4j) es arquitectura objetivo pero todavía no forma parte de este repo — ver "Limitaciones y próximos pasos". El resto de la arquitectura propuesta originalmente (Motor A de ML, NLP sobre el Boletín Oficial, persistencia real en Postgres) ya está implementado, ver las secciones siguientes.

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
python -m spacy download es_core_news_sm   # modelo NER en español (services/nlp_service.py)
cp .env.example .env   # editar credenciales de Postgres
docker compose up -d   # levanta Postgres+PostGIS con el esquema ya aplicado
```

La persistencia en Postgres (`database/`) es **opcional**: si no hay
conexión disponible (no corriste `docker compose up -d`, o no configuraste
`PG_HOST`/`PG_PORT`/`PG_DB`/`PG_USER`/`PG_PASSWORD` en `config/settings.py`
o el entorno), `pipeline.py` lo detecta con
`database.connection.verificar_conexion()`, loguea una advertencia y sigue
funcionando igual — solo con `dashboard/data.json` como salida, misma
filosofía que la ingesta de indicadores macro cayendo a valores de
referencia si la API del Banco Mundial no responde.

## Uso

```bash
# Solo indicadores macro reales (CPI/WGI) -> dashboard/data.json
python pipeline.py

# Con tus propios datos reales de contrataciones
python pipeline.py --ofertas ofertas.csv --licitaciones licitaciones.csv --adendas adendas.csv

# --entidades es opcional: solo hace falta para REGLA-004/REGLA-005 del
# motor de patrones (mismo domicilio / mismo representante técnico)
python pipeline.py --licitaciones licitaciones.csv --entidades entidades.csv

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

## Motor de concentración y motor de redes — `services/`

`services/concentration_service.py` extiende `analytics/finanzas.hhi_por_organismo`
(que ya calcula HHI y proveedor dominante) con concentración Top 3, Top 5,
por categoría/rubro y evolución temporal, sin duplicar el cálculo de
cuotas de mercado. `services/network_service.py` extiende
`analytics/sna.py` (que ya calcula betweenness y comunidades Louvain) con
degree, closeness y PageRank, y arma un `network_score` 0-100 por
entidad, combinación ponderada y documentada (no una caja negra).

## Motor de patrones — `services/pattern_service.py`

Ocho reglas de negocio explicables sobre licitaciones/ofertas/adendas/
entidades reales (peso máximo combinado: 100 puntos):

| Regla | Qué detecta | Peso |
|---|---|---|
| REGLA-001 | Proveedor concentra > 50% del gasto del organismo | 20 |
| REGLA-002 | Cantidad de ofertas = 1 (sin competencia real) | 15 |
| REGLA-003 | Empresa gana repetidamente al mismo organismo | 15 |
| REGLA-004 | Mismo domicilio entre empresas oferentes | 10 |
| REGLA-005 | Mismo representante técnico/apoderado | 10 |
| REGLA-006 | Contratos consecutivos al mismo organismo en ventanas cortas | 10 |
| REGLA-007 | Incremento contractual atípico (low-balling vía adendas) | 10 |
| REGLA-008 | Concentración elevada + baja competencia | 10 |

Cada regla solo se activa si hay evidencia real en los datos provistos
(ver `services/pattern_service.construir_tabla_patrones`); si falta una
tabla completa (ej. no se subió `entidades.csv`), las reglas que dependen
de ella no se activan, en vez de asumírseles un valor.

## Índice IRCS — `services/risk_service.py`

Índice de Riesgo de Corrupción Sistémica, 0-100, por licitación/empresa:

```
IRCS = 20% anomalías + 20% concentración + 20% redes
     + 15% patrones + 15% opacidad + 10% institucional
```

Cada componente sale de un cálculo real ya hecho por otro módulo (HHI,
`network_score`, `score_patrones`, % de campos clave publicados, CPI/WGI
reales ya ingeridos, y el **Motor A** para anomalías — ver más abajo). El
componente que no tenga evidencia real disponible se excluye del cálculo
y los pesos se redistribuyen proporcionalmente entre los disponibles, en
vez de asumírsele un valor neutro.

**Importante:** el IRCS es un score de **riesgo**, no una acusación ni
una prueba de delito. Señala dónde mirar con más atención; la
responsabilidad la determina una investigación real, no un algoritmo.

## Motor A — Anomalías con ML no supervisado (`ml/`)

`services/risk_service.componente_anomalias()` intenta primero el Motor A
real (`ml/scoring.py`), y si scikit-learn no está instalado o hay menos
de `ml.isolation_forest.MIN_FILAS` licitaciones para entrenar, cae de
forma transparente a la heurística estadística anterior (z-score sobre
el monto adjudicado) — misma filosofía de fallback documentado que el
resto del sistema, nunca falla en silencio ni inventa un score.

El Motor A combina 3 modelos no supervisados de scikit-learn sobre
`monto_adjudicado`, `cantidad_ofertas`, `duracion`, `modificaciones` y
`proveedor_participacion`:

```
anomaly_score = 100 × (0.4 × IsolationForest + 0.4 × LOF + 0.2 × DBSCAN-outlier)
```

Como los modelos de ML no son inherentemente explicables, `ml/scoring.py`
agrega **factores** post-hoc (ej. `"monto_atipico"`, `"duracion_atipica"`)
calculados con z-score sobre cada feature individual, para que cada score
alto tenga una razón auditable y no sea una caja negra.

## NLP sobre el Boletín Oficial (`services/nlp_service.py`)

Extracción de entidades nombradas sobre texto real (hoy vía
`POST /api/v1/documentos/procesar`; pensado para el texto de avisos que
trae `ingestion/bora_boletin.py`). Enfoque híbrido, decidido tras probar
el modelo chico de spaCy en español contra texto legal/administrativo
real:

- **PERSONA**: spaCy (`es_core_news_sm`) — funciona bien en este dominio.
- **EMPRESA** y **ORGANISMO**: regex/heurística por palabras clave
  (sufijos legales S.A./S.R.L./S.A.S./S.A.C.I./S.C.A./U.T.E.; listado de
  organismos públicos y siglas conocidas), porque el modelo chico de
  spaCy confunde sistemáticamente ORG con LOC en este tipo de texto —
  se documenta la decisión en `services/nlp_service.py`.
- **CUIT, montos ($ / ARS) y expedientes** (`EX-YYYY-NNNNNNNN-...`):
  regex determinístico, no depende de ningún modelo.

Si spaCy o el modelo en español no están instalados, la extracción de
PERSONA cae a `[]` en vez de romper el resto del endpoint (mismo patrón
de degradación explícita que el resto del sistema); el campo
`motor_personas` de la respuesta indica qué motor se usó realmente.

**Alcance de esta pieza:** no incluye scraping del cuerpo completo de
avisos de BORA todavía (ver "Limitaciones y próximos pasos"); tampoco
persiste las entidades extraídas — no se agregó una tabla nueva a
`db/schema.sql` sin que sea una decisión explícita del equipo (ver
sección de Persistencia).

## Persistencia real en Postgres (`database/`)

Además de `dashboard/data.json`, cada corrida de `pipeline.py` puede
persistir en el Postgres real de `db/schema.sql` (ORM SQLAlchemy 2.0 en
`database/models.py`, mapeado 1:1 a las 15 tablas del esquema):

- **Entidades** (`entidad`): upsert por `identificador_fiscal` si está
  disponible, si no por `(nombre, tipo)` — un organismo/empresa no se
  duplica entre corridas sucesivas sobre el mismo CSV.
- **Licitaciones** (`licitacion`): upsert idempotente por
  `fuente_id_externo` (el `licitacion_id` del CSV) — se actualiza in
  place, no se duplica.
- **Indicadores macro** (`indicador_macro`): upsert idempotente por
  `(pais_iso3, anio, indicador)`.
- **Aristas del grafo** (`grafo_arista`) y **scores de riesgo**
  (`score_riesgo`): **no** son idempotentes a propósito — cada corrida
  agrega filas nuevas, para que quede un historial real de cómo
  evolucionó la red y el IRCS entre corridas sucesivas (limitación
  conocida: `grafo_arista` no tiene una clave natural única en el
  esquema actual para deduplicar sin una migración).

Si no hay conexión a Postgres disponible, el pipeline lo detecta con
`database.connection.verificar_conexion()` y sigue funcionando igual solo
con `dashboard/data.json` — nunca se cae por esto (ver "Instalación").

**Alcance de esta fase:** el foco fue que el pipeline escriba en Postgres
de forma correcta e idempotente donde corresponde. Los endpoints de
lectura de `/api/v1/*` siguen leyendo del último `dashboard/data.json`
(vía `services/data_store.py`), no consultan Postgres directamente
todavía — eso queda para una fase siguiente si hace falta servir
histórico completo por API en vez de solo la última corrida.

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
| GET | `/procurement/{bloque}` | co_presentismo, asimetria_victorias, hhi_por_organismo, low_balling, ... |
| GET | `/scoring/reglas` | Reglas de scoring vigentes (`analytics/scoring.py`, transparencia del modelo) |
| POST | `/scoring/evaluar` | Score + audit card para una fila de indicadores real |
| POST | `/pipeline/ejecutar` | Dispara una corrida manual (acepta CSV reales por multipart, incl. `entidades`) |

Endpoints nuevos, organizados por recurso bajo `/api/v1` (no reemplazan a
los de arriba, que se mantienen por compatibilidad hacia atrás):

| Método | Ruta | Uso |
|---|---|---|
| GET | `/api/v1/contratos` | Todos los bloques calculados (HHI, Top3/Top5, low-balling, redes, patrones, riesgo_ircs, ...) |
| GET | `/api/v1/contratos/{bloque}` | Un bloque puntual (404 si el nombre no existe) |
| GET | `/api/v1/empresas` | Lista de proveedores con IRCS calculado |
| GET | `/api/v1/empresas/{identificador}` | Vista consolidada de una empresa (contrataciones + riesgo + detalle) |
| GET | `/api/v1/redes` | Métricas de red de todas las entidades del grafo de adjudicaciones |
| GET | `/api/v1/redes/empresa/{identificador}` | degree/betweenness/closeness/PageRank/comunidad/`network_score` de una entidad |
| GET | `/api/v1/patrones/reglas` | Las 8 reglas vigentes del motor de patrones |
| GET | `/api/v1/patrones` | Resultado de las 8 reglas sobre la última corrida |
| POST | `/api/v1/riesgo/ircs` | Calcula el IRCS a partir de los 6 componentes que se le pasen |
| GET | `/api/v1/riesgo/empresa/{identificador}` | IRCS máximo observado para una empresa |
| GET | `/api/v1/alertas` | Alertas explicables derivadas de patrones + IRCS (código, descripción, severidad) |
| POST | `/api/v1/documentos/procesar` | NER (personas/empresas/organismos/CUIT/montos/expedientes) sobre texto real |

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
- **NLP sobre el Boletín Oficial — cuerpo completo de avisos**: el
  NER (`services/nlp_service.py`) ya funciona sobre cualquier texto real
  vía `POST /api/v1/documentos/procesar`; lo que falta es que
  `ingestion/bora_boletin.py` traiga el texto completo de cada aviso (hoy
  trae metadatos/listado) para correr el NER automáticamente sobre cada
  publicación nueva y persistir las entidades extraídas — eso último
  requeriría además una tabla nueva en `db/schema.sql`, que no se agregó
  unilateralmente en esta fase (ver "Persistencia real en Postgres").
- **API de lectura vs. Postgres**: `pipeline.py` ya persiste en Postgres
  (entidades, licitaciones, aristas, scores, indicadores macro — ver
  "Persistencia real en Postgres"), pero los endpoints de `/api/v1/*`
  todavía leen del último `dashboard/data.json` en vez de consultar la
  base directamente; migrarlos daría acceso al histórico completo entre
  corridas (hoy solo se ve la última) en vez de un snapshot.
- **Grafo de aristas sin clave natural**: `grafo_arista` no tiene una
  columna única en `db/schema.sql` para deduplicar contra corridas
  anteriores sin una migración; por diseño, `persistir_grafo_aristas`
  inserta una fila nueva por corrida (queda como historial), pero eso
  significa que la tabla crece sin límite si el pipeline corre muy
  seguido — considerar una migración con `(origen_id, destino_id,
  tipo_relacion, corrida_id)` si se vuelve un problema de volumen.
- **Integración con el hub Mapa de Transparencia**: este repo expone la
  API lista para ser consumida, pero la integración en sí (autenticación
  entre servicios, formato exacto que espera el hub, etc.) queda pendiente
  hasta que ese ecosistema esté definido.
