# Pipeline

Este documento describe el pipeline completo del repositorio: cómo
se verifica cada cambio, cómo se construye y publica la imagen SHA8 y cómo se promociona por digest cuando staging y prod apuntan al mismo commit. Es la
referencia canónica para RA1 y RA2 — si entiendes este fichero,
entiendes el sistema de entrega.

> Prerrequisito: tener el runner autoalojado y los Environments
> configurados. Ver [`docs/setup.md`](setup.md).

## Vista general

El repo separa claramente verificación y entrega:

- **CI** (`ci.yml`) corre en `ubuntu-latest` hospedado por GitHub y nunca
  despliega. Se ejecuta en `pull_request` y en `push` a `main`.
- **CD** construye y publica la imagen SHA8 en `cd-dev.yml` tras un CI exitoso de `push` a `main`. `cd-staging.yml` y `cd-prod.yml` promocionan el digest existente sin reconstruir; sus `ci-gate` exigen que el commit sea ancestro de `origin/main` y tenga CI exitoso de `push` a `main`. `rollback.yml` redespliega un tag existente.

El reusable publica en `ghcr.io/<dueño-del-repo-en-minúsculas>/hiss`, también en forks. Los CD despliegan con `IMAGE_TAG=<tag>@<digest>` y `APP_VERSION=<tag>` mediante el mismo Compose; el digest identifica el artefacto. El build de CI solo valida la construcción y no es la imagen publicada.

## CI — `.github/workflows/ci.yml`

`ci.yml` es el único workflow que responde a `pull_request`. Su objetivo
es dar feedback rápido sin tocar ningún entorno.

```yaml
on:
  pull_request:
  push:
    branches: [main]
```

Propiedades clave:

- `permissions: contents: read` por defecto; `changes` añade `pull-requests: read`.
- `concurrency: group: ci-... / cancel-in-progress: para PR` — cancela
  ejecuciones obsoletas de la misma rama.
- Todos los jobs en `ubuntu-latest` con `timeout-minutes` acotado. Una
  ejecución normal termina en menos de tres minutos.

### Jobs

| Job | Cuándo corre | Qué hace |
| --- | --- | --- |
| `changes` | siempre | `dorny/paths-filter@v3` clasifica el diff en `app`, `cli` y `shared` (`pytest.ini`, `ruff.toml`, `.github/workflows/**`, `deploy/**`, `compose.yml`). Exporta `outputs.app/cli/shared`. |
| `lint-pipeline` | siempre | actionlint 1.7.12 y `docker compose config -q` para ambos Compose y los tres env-files con valores ficticios. |
| `lint` | `app`/`cli`/`shared` | `setup-python@v5` con Python 3.13 y caché de `app/requirements.txt` + `cli/requirements.txt`; `pip install ruff==0.9.10`; `ruff check app cli` y `ruff format --check app cli`. |
| `lint-docker` | `app` | `docker run --rm -i hadolint/hadolint:v2.12.0-alpine < app/Dockerfile`. |
| `test-app` | `app`/`shared` | Servicio efímero `postgres:17-alpine` (`POSTGRES_DB=hiss_test`, `healthcheck pg_isready`), `DATABASE_URL=postgresql://postgres:postgres@localhost:5432/hiss_test`, instala `app/requirements-dev.txt`, ejecuta `alembic -c app/alembic.ini upgrade head` y `pytest app/tests`. |
| `test-cli` | `cli`/`shared` | Sin servicio; `pip install -r cli/requirements.txt` + `pip install -e cli`; `pytest cli/tests`. |
| `build` | `app` y `test-app` ok | `docker build -f app/Dockerfile app/` — solo valida que la imagen construye, sin `login` ni `push`. |

El filtro de rutas evita trabajo inútil: un cambio solo en `cli/` no
dispara `test-app` ni `lint-docker`; un cambio solo en documentación deja
jobs saltados que GitHub reporta como éxitos para no bloquear el merge. Los
checks requeridos de `main` incluyen `CI / Detect changes`,
`CI / Validate workflows and Compose`, `CI / Lint Python`, `CI / Lint Dockerfile`, `CI / Test app`, `CI / Test CLI`
y `CI / Build app image`, si se configuran como requeridos (ver `docs/setup.md`).

### Revisar una ejecución de CI

```sh
gh run list --workflow ci.yml --limit 5
gh run watch <run-id> --exit-status
gh run view <run-id> --log-failed
```

## CD — construcción, publicación y despliegue

Tres workflows despliegan automáticamente según el trigger y uno permite volver atrás manualmente:

```
dev:          prepare → build SHA8 (reutilizable) → deploy → smoke-test
staging/prod: ci-gate → prepare → promote (job build reutilizable) → deploy → smoke-test
rollback:     deploy → smoke-test
```

Deploy y smoke usan `self-hosted`; con varios runners hay que asegurar que ambos jobs lleguen al mismo host. CD y rollback comparten `cd-<environment>` con `cancel-in-progress: false`; la concurrencia no garantiza una cola FIFO.

### Tabla de triggers

| Disparador | Workflow | Tag de imagen | Environment | Puerto | Puerta |
| --- | --- | --- | --- | --- | --- |
| CI en verde tras `push` a `main` | `cd-dev.yml` | `head_sha` truncado a 8 caracteres | `dev` | `8001` | CI debe ser `success` |
| `push` de tag `X.Y.Z-snapshot` | `cd-staging.yml` | `X.Y.Z-snapshot` | `staging` | `8002` | job `ci-gate` + automático |
| `push` de tag `X.Y.Z` | `cd-prod.yml` | `X.Y.Z` | `prod` | `8003` | job `ci-gate` + aprobación de Environment |
| `workflow_dispatch` | `rollback.yml` | tag elegido manualmente | `dev`/`staging`/`prod` | según Environment | aprobación si es `prod` |

Los tags no llevan `v` inicial. `pull_request` nunca despliega — cada
`cd-*.yml` y `rollback.yml` lo declara en su cabecera:

```yaml
# Safety invariant: this workflow deploys only after CI succeeds for an
# owner-controlled push to main. Never add pull_request.
```

### `_build-push.yml` — workflow reutilizable

`.github/workflows/_build-push.yml` es `workflow_call` con `tag` obligatorio y `ref` y `source_tag` opcionales; expone `image` y `digest`:

```yaml
on:
  workflow_call:
    inputs:
      tag: { description: Image tag to publish, required: true, type: string }
      ref: { description: Git ref or SHA to check out, required: false, type: string, default: "" }
      source_tag: { description: Existing commit image tag to promote, required: false, type: string, default: "" }
    outputs:
      digest: { value: '${{ jobs.build.outputs.digest }}' }
      image: { value: '${{ jobs.build.outputs.image }}' }
permissions:
  contents: read
  packages: write
```

Con `source_tag` vacío, el job consulta el tag SHA8: si no existe, construye el `ref` y lo publica mediante `docker/build-push-action@v6`; en las reejecuciones reutiliza el digest ya publicado tras verificar la revisión OCI completa. Si la revisión falta o no coincide, o no se puede consultar el registro, falla sin reconstruir. Si se pasa `source_tag`, consulta su digest, comprueba que la etiqueta OCI `org.opencontainers.image.revision` corresponda al SHA completo de `ref` y crea el Release Tag con `imagetools create`; después comprueba que el digest no haya cambiado. Si no existe la imagen SHA8 o falta/no coincide la revisión, falla. Los callers pasan `contents: read` y `packages: write` al job reutilizable; no usan `secrets: inherit`. El `GITHUB_TOKEN` está disponible automáticamente. Ver `docs/teacher/workflow-refactor-lesson.md` para el refactor histórico.

### `cd-dev.yml`, `cd-staging.yml`, `cd-prod.yml`

Los tres comparten estructura. Ejemplo `cd-dev.yml`:

- `prepare` (solo si CI fue `success` en un `push` a `main`): `runs-on: ubuntu-latest`, tag = 8 primeros caracteres de `github.event.workflow_run.head_sha`.
- `build`: reutilizable `_build-push.yml` con `ref` al mismo SHA.
- `deploy`: `runs-on: [self-hosted]`, `environment: dev`, `env: DEPLOY_TAG` y
  `POSTGRES_PASSWORD: ${{ secrets.POSTGRES_PASSWORD }}`, pasos `checkout@v7`,
  `docker compose ... pull` con `IMAGE_TAG="$DEPLOY_TAG@$DIGEST"` y `APP_VERSION="$DEPLOY_TAG"`, seguido de `up -d --no-build --pull never`.
- `smoke-test`: `runs-on: [self-hosted]`, `BASE_URL=http://localhost:8001`,
  tres `curl --fail --silent --show-error --max-time 10 --retry 10 --retry-delay 2 --retry-connrefused`
  a `/healthz`, `/readyz` y `/version | jq --exit-status --arg expected \"$DEPLOY_TAG\" '.version == $expected'`.

`cd-dev.yml` se dispara con `on: workflow_run` del workflow `CI`
(`types: [completed]`). Los jobs de `prepare` exigen `conclusion == success`,
`event == push` y `head_branch == main` para que un CI verde de un pull
request no despliegue. `cd-staging.yml` usa `on: push: tags:
'[0-9]+.[0-9]+.[0-9]+-snapshot'` y `RELEASE_TAG: ${{ github.ref_name }}`;
`BASE_URL=http://localhost:8002`. `cd-prod.yml` usa `'[0-9]+.[0-9]+.[0-9]+'`
y `BASE_URL=http://localhost:8003` con `environment: prod` protegido por
revisor. Staging y prod empiezan por `ci-gate`, que consulta el CI de ese
commit: exige ascendencia de `origin/main` y consulta CI de `push` a `main`; no deja pasar `prepare` hasta `completed:success` (o falla si CI falló o agotó la espera). Es necesario que `cd-dev` ya haya publicado el SHA8 correspondiente.

### `rollback.yml`

Solo `workflow_dispatch` con inputs `environment` (`dev`/`staging`/`prod`,
`type: choice`) y `tag` (`type: string`). No construye: redespliega un tag
existente por su tag (sin fijar digest). `deploy` elige `env_file`/`project` con `case`, hace
`pull` y `up -d --no-build --pull never`; `smoke-test` resuelve `BASE_URL` según el Environment y
repite los tres `curl` + `jq`. Los rollbacks a `prod` también pausan por
aprobación de Environment.

```sh
gh workflow run rollback.yml -f environment=prod -f tag=0.1.0
gh workflow run rollback.yml -f environment=staging -f tag=0.1.0-snapshot
```

## Diagramas

### Flujo por tipo de disparador

```mermaid
flowchart TD
    PR["pull_request / push a main<br/>ci.yml en ubuntu-latest"] --> CHANGES["changes<br/>dorny/paths-filter"]
    PR --> LP["lint-pipeline<br/>actionlint + Compose config"]
    CHANGES --> LINT["lint<br/>ruff 0.9.10"]
    CHANGES --> LINTD["lint-docker<br/>hadolint"]
    CHANGES --> TAPP["test-app<br/>postgres:17-alpine efímero"]
    CHANGES --> TCLI["test-cli"]
    TAPP --> BUILD["build<br/>docker build -f app/Dockerfile app/"]

    PUSHMAIN["push a main"] --> CIWAIT["ci.yml debe terminar en success"]
    CIWAIT --> CDDEV["cd-dev.yml via workflow_run<br/>prepare SHA8 → _build-push.yml<br/>→ deploy dev:8001 → smoke-test"]
    TAGSNAP["push tag X.Y.Z-snapshot"] --> CDSTAG["cd-staging.yml<br/>ci-gate → prepare → promoción SHA8/digest<br/>→ deploy staging:8002 → smoke-test"]
    TAGREL["push tag X.Y.Z"] --> CDPROD["cd-prod.yml<br/>ci-gate → prepare → promoción SHA8/digest<br/>→ deploy prod:8003<br/>gate de aprobación → smoke-test"]
    WD["workflow_dispatch"] --> ROLLBACK["rollback.yml<br/>deploy Environment/tag elegido<br/>→ smoke-test"]

    classDef cd fill:#e1f5fe,stroke:#01579b
    class CDDEV,CDSTAG,CDPROD,ROLLBACK cd
```

### Delivery vs Deployment — el gate de `prod`

```mermaid
sequenceDiagram
    participant D as dev :8001
    participant S as staging :8002
    participant P as prod :8003
    participant R as Revisor

    Note over D,P: push a main + CI verde → dev despliega — Deployment
    D->>D: _build-push SHA8 + pull/up + smoke-test

    Note over D,P: push X.Y.Z-snapshot → staging automático — Deployment
    S->>S: promover SHA8 por digest + pull/up + smoke-test

    Note over D,P: push X.Y.Z → prod queda en espera — Delivery
    P->>R: Environment prod requiere aprobación
    R-->>P: Approve
    P->>P: pull/up X.Y.Z@digest + smoke-test
    Note over D,P: Sin aprobación no hay despliegue — Delivery != Deployment
```

La distinción nace de `environment: prod` con `Required reviewers` en
`Settings → Environments`. `dev` y `staging` practican Continuous
Deployment; `prod` practica Continuous Delivery.

## Smoke tests y probes

Cada despliegue, incluido `rollback.yml`, verifica tres endpoints expuestos
por `app/app/api/probes.py`:

- `GET /healthz` — liveness sin tocar la base de datos, siempre `200` si el
  proceso responde.
- `GET /readyz` — readiness con `SELECT 1` real contra Postgres; `503` si la
  base de datos no es alcanzable.
- `GET /version` — devuelve `{"version": "<APP_VERSION>"}`; el smoke test
  comprueba `jq --exit-status --arg expected \"$DEPLOY_TAG\" '.version == $expected'`
  (forma corta: `jq -e --arg expected`). Es una comprobación de la configuración de runtime, no prueba independiente del SHA ni del digest; estos se verifican en la promoción.

La healthcheck de Compose en `deploy/compose.yml` usa
`python -c 'import urllib.request; urllib.request.urlopen(\"http://localhost:8000/healthz\")'`
(no `curl`, ausente en `python:3.13-slim`) y `depends_on: db: condition: service_healthy`
con `pg_isready`. El observador en el runner hace `curl` desde el host con
`--retry 10 --retry-delay 2 --retry-connrefused` para tolerar el arranque.

```sh
curl --fail http://localhost:8001/healthz | jq .
curl --fail http://localhost:8001/readyz  | jq .
curl --fail http://localhost:8001/version | jq .  # {"version":"<SHA8>"}
curl --fail http://localhost:8002/version | jq .  # {"version":"X.Y.Z-snapshot"}
curl --fail http://localhost:8003/version | jq .  # {"version":"X.Y.Z"}

# Comando exacto del workflow (con reintentos y validación de versión):
curl --fail --silent --show-error --max-time 10 --retry 10 --retry-delay 2 --retry-connrefused "$BASE_URL/healthz"
curl --fail --silent --show-error --max-time 10 --retry 10 --retry-delay 2 --retry-connrefused "$BASE_URL/readyz"
curl --fail --silent --show-error --max-time 10 --retry 10 --retry-delay 2 --retry-connrefused "$BASE_URL/version" \
  | jq --exit-status --arg expected "$DEPLOY_TAG" '.version == $expected' >/dev/null
# forma mínima equivalente: jq -e --arg expected "$DEPLOY_TAG" '.version == $expected'
```

## Invariantes y convenciones

- El workflow deriva `IMAGE` del dueño y usa `IMAGE_TAG=tag@digest` y `APP_VERSION=tag`; el despliegue inyecta `POSTGRES_PASSWORD=${{ secrets.POSTGRES_PASSWORD }}` sin versionarla.
- `COMPOSE_PROJECT_NAME` (`hiss-dev`/`hiss-staging`/`hiss-prod`) aísla redes,
  volúmenes `pgdata` y contenedores en el mismo host.
- Por convención `X.Y.Z-snapshot` puede moverse y `X.Y.Z` no; GitHub no impone esa inmutabilidad sin reglas externas.
- `rollback.yml` nunca construye — solo mueve el tag desplegado.

Ver también [`docs/environments.md`](environments.md) para el mapeo de
entornos y [`docs/release-process.md`](release-process.md) para la ceremonia
de promoción.
