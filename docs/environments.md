# Entornos

Este documento explica cómo los cuatro entornos del temario se realizan en
tres despliegues persistentes más un entorno efímero de CI. Si
`docs/pipeline.md` es el cómo, este es el dónde.

## Los cuatro entornos del temario vs los tres despliegues del repo

El temario del módulo 5168 distingue cuatro entornos:

| Entorno del temario | Propósito | Realización en hiss | Persistente | Puerto / detalle |
| --- | --- | --- | --- | --- |
| Development | integración diaria del equipo | `dev` — `hiss-dev` en tu máquina | sí | `8001` — `deploy/dev.env` |
| Testing / QA | verificación automática | entorno efímero de CI (`test-app`) | no | service container `postgres:17-alpine` en `ci.yml` |
| Staging | preproducción idéntica a prod | `staging` — `hiss-staging` | sí | `8002` — `deploy/staging.env` |
| Production | usuarios finales | `prod` — `hiss-prod` | sí | `8003` — `deploy/prod.env` + gate de aprobación |

La decisión de no tener un QA persistente es deliberada: el módulo pide
un entorno de pruebas automatizadas, no una réplica permanente. Lo
realizamos como el job `test-app` con un Postgres efímero, que es más
fiel a la práctica de CI moderna y evita mantener una cuarta pila
idéntica solo para ejecutar `pytest`.

Cada despliegue persistente usa el mismo `deploy/compose.yml` con distinto
`--env-file` y `COMPOSE_PROJECT_NAME`. Los tres pueden coexistir en el
mismo host:

```sh
export POSTGRES_PASSWORD='elige-un-secreto-local'
export IMAGE_TAG="$(git rev-parse --short=8 HEAD)" APP_VERSION="$(git rev-parse --short=8 HEAD)" # SHA8 publicado
docker compose -f deploy/compose.yml --env-file deploy/dev.env -p hiss-dev up -d
unset IMAGE_TAG APP_VERSION  # usa los tags de cada env-file para staging/prod
docker compose -f deploy/compose.yml --env-file deploy/staging.env -p hiss-staging up -d
docker compose -f deploy/compose.yml --env-file deploy/prod.env -p hiss-prod up -d
IMAGE_TAG="$(git rev-parse --short=8 HEAD)" APP_VERSION="$(git rev-parse --short=8 HEAD)" docker compose --env-file deploy/dev.env -p hiss-dev ps
docker compose --env-file deploy/staging.env -p hiss-staging ps
docker compose --env-file deploy/prod.env -p hiss-prod ps
```

El responsable del repositorio publicará `0.1.0-snapshot` y `0.1.0` en `ghcr.io/mvieitesr/hiss` antes de la práctica; usa un SHA8 publicado para dev. Para un fork exporta `IMAGE=ghcr.io/<dueño-en-minúsculas>/hiss`. Consulta [`docs/setup.md`](setup.md) para la guía completa.

## Local Stack manual con GHCR del fork

Este recorrido es independiente del CD: construye y publica una imagen manual, no el digest que construye `cd-dev`. Necesitas Docker, un checkout limpio en el commit elegido, un paquete GHCR accesible y un token clásico con permisos de paquetes del propietario. No publiques credenciales ni las introduzcas en el historial. Sustituye `tu-usuario` por el dueño del fork en minúsculas:

```bash
export OWNER=tu-usuario
export IMAGE="ghcr.io/$OWNER/hiss"
export IMAGE_TAG="$(git rev-parse --short=8 HEAD)-manual"
export APP_VERSION="$IMAGE_TAG"
export POSTGRES_PASSWORD='elige-un-secreto-local' APP_PORT=8011
# El token se lee sin eco; usa configuración Docker temporal. Docker puede usar
# un gestor de credenciales del sistema si está disponible.
export DOCKER_CONFIG="$(mktemp -d)"
read -r -s -p 'GHCR token: ' GHCR_TOKEN; echo
printf '%s' "$GHCR_TOKEN" | docker login ghcr.io -u "$OWNER" --password-stdin
unset GHCR_TOKEN

docker build -f app/Dockerfile -t "$IMAGE:$IMAGE_TAG" app/
docker push "$IMAGE:$IMAGE_TAG"
docker compose -f deploy/compose.yml --env-file deploy/dev.env -p hiss-localstack pull
docker compose -f deploy/compose.yml --env-file deploy/dev.env -p hiss-localstack up -d --no-build --pull never --wait --wait-timeout 60
curl --fail http://localhost:8011/healthz
curl --fail http://localhost:8011/readyz
curl --fail http://localhost:8011/version
# Borra la configuración temporal de Docker cuando termines los pulls.
rm -rf "$DOCKER_CONFIG"; unset DOCKER_CONFIG
# down -v elimina también la base de este proyecto desechable:
docker compose -f deploy/compose.yml --env-file deploy/dev.env -p hiss-localstack down -v
unset OWNER IMAGE IMAGE_TAG APP_VERSION POSTGRES_PASSWORD APP_PORT
```

La imagen manual puede tener un digest distinto al de CD aunque comparta fuente. El sufijo `-manual` evita pisar el SHA8 de CD; la promoción de CD también exige la etiqueta OCI de revisión generada por su build. Revisa los permisos y la visibilidad del paquete como indica [`docs/setup.md`](setup.md). El token y la configuración Docker temporal son sensibles mientras existan.

## Configuración por Environment

Los tres `deploy/*.env` están versionados y contienen solo configuración no
secreta. La contraseña nunca aparece en ellos — se inyecta desde
`secrets.POSTGRES_PASSWORD` en cada `cd-*.yml` y `rollback.yml`.

| Variable | `dev` (`deploy/dev.env`) | `staging` (`deploy/staging.env`) | `prod` (`deploy/prod.env`) |
| --- | --- | --- | --- |
| `COMPOSE_PROJECT_NAME` | `hiss-dev` | `hiss-staging` | `hiss-prod` |
| `IMAGE` | `ghcr.io/mvieitesr/hiss` | `ghcr.io/mvieitesr/hiss` | `ghcr.io/mvieitesr/hiss` |
| `IMAGE_TAG` | vacío (inyectar SHA8) | `0.1.0-snapshot` | `0.1.0` |
| `APP_VERSION` | vacío (inyectar SHA8) | `0.1.0-snapshot` | `0.1.0` |
| `APP_PORT` | `8001` | `8002` | `8003` |
| `FEATURE_LABEL_FILTERING` | `true` | `true` | `false` |
| `POSTGRES_DB` | `hiss` | `hiss` | `hiss` |
| `POSTGRES_USER` | `postgres` | `postgres` | `postgres` |
| `POSTGRES_PASSWORD` | *(inyectada)* | *(inyectada)* | *(inyectada)* |

El shell puede sobrescribir `IMAGE` y los demás valores del env-file. En CD, `IMAGE` se deriva del dueño, `IMAGE_TAG` recibe `tag@digest` y `APP_VERSION` el tag; son independientes. Por ejemplo, con `IMAGE`, `DEPLOY_TAG`, `DIGEST` y contraseña ya exportados:

```sh
IMAGE_TAG="$DEPLOY_TAG@$DIGEST" APP_VERSION="$DEPLOY_TAG" \
  docker compose -f deploy/compose.yml --env-file deploy/staging.env -p hiss-staging pull
```

`/version` solo refleja `APP_VERSION`, no prueba el digest ni la revisión por sí sola. `APP_TAG` no existe como variable de Compose.

La base de datos de cada Environment es independiente (`pgdata` por proyecto).
La app solo expone `APP_PORT:8000`; `5432` nunca se publica en el host para
evitar colisiones con un Postgres local.

## Testing / QA efímero — el service container de CI

`ci.yml:jobs:test-app` declara:

```yaml
services:
  postgres:
    image: postgres:17-alpine
    env: { POSTGRES_DB: hiss_test, POSTGRES_USER: postgres, POSTGRES_PASSWORD: postgres }
    ports: ["5432:5432"]
    options: >-
      --health-cmd "pg_isready -U postgres -d hiss_test"
      --health-interval 5s --health-timeout 5s --health-retries 10 --health-start-period 5s
env:
  DATABASE_URL: postgresql://postgres:postgres@localhost:5432/hiss_test
steps:
  - run: alembic -c app/alembic.ini upgrade head
  - run: pytest app/tests
```

El servicio vive solo durante el job, aplica migraciones reales y ejecuta
los tests de Flask contra Postgres — no SQLite en memoria. Es el entorno de
QA del temario: automatizado, desechable y fiel a producción. Cuando el job
termina, el contenedor desaparece sin rastro.

`test-cli` corre sin servicio, lo que demuestra que no todo necesita base
de datos.

## Aislamiento con Compose

`deploy/compose.yml` declara `name: ${COMPOSE_PROJECT_NAME:-hiss-dev}` y dos
servicios:

- `db` — `postgres:17-alpine`, `healthcheck: pg_isready -U ${POSTGRES_USER:-postgres} -d ${POSTGRES_DB:-hiss}`,
  volumen `pgdata`, sin `ports` publicados.
- `app` — `image: ${IMAGE}:${IMAGE_TAG}`, `build: context: ../app`,
  `depends_on: db: condition: service_healthy`,
  `ports: ["${APP_PORT:-8001}:8000"]`,
  `DATABASE_URL: postgresql://${POSTGRES_USER:-postgres}:${POSTGRES_PASSWORD:?must be set}@db:5432/${POSTGRES_DB:-hiss}`,
  `APP_VERSION` y `FEATURE_LABEL_FILTERING`,
  `healthcheck: python -c 'import urllib.request; urllib.request.urlopen(\"http://localhost:8000/healthz\")'`.

El volumen `pgdata` es por proyecto Compose; `hiss-dev`, `hiss-staging` y
`hiss-prod` no comparten datos. Para borrar un Environment sin perder los
otros:

```sh
export POSTGRES_PASSWORD='elige-un-secreto-local'
export IMAGE_TAG="$(git rev-parse --short=8 HEAD)" APP_VERSION="$(git rev-parse --short=8 HEAD)"
docker compose --env-file deploy/dev.env -p hiss-dev down      # mantiene pgdata
docker compose --env-file deploy/dev.env -p hiss-dev down -v   # borra pgdata de dev
```

> Nota: la demo blue-green (`deploy/blue-green/compose.yml`) usa
> `postgres:16-alpine` y puerto `9000` en el proxy — es una isla
> independiente documentada en `deploy/blue-green/README.es.md` y
> `docs/deployment-strategies.md`.

## Diagrama de promoción

```mermaid
flowchart LR
    subgraph QA["QA efímero - CI"]
        TAPP["test-app<br/>postgres:17-alpine<br/>alembic + pytest"]
    end

    DEV["dev<br/>hiss-dev:8001<br/>SHA8<br/>auto"] --> STAG["staging<br/>hiss-staging:8002<br/>X.Y.Z-snapshot<br/>auto"]
    STAG --> PROD["prod<br/>hiss-prod:8003<br/>X.Y.Z<br/>gate aprobación"]

    PR["pull_request / push"] --> TAPP
    CI["CI success: push a main"] --> DEV

    TAGSNAP["push tag<br/>X.Y.Z-snapshot"] --> STAG
    TAGREL["push tag<br/>X.Y.Z"] --> PROD

    ROLLBACK["rollback.yml<br/>workflow_dispatch"] -.-> DEV
    ROLLBACK -.-> STAG
    ROLLBACK -.-> PROD

    classDef env fill:#fff3e0,stroke:#e65100
    class DEV,STAG,PROD env
    classDef qa fill:#f3e5f5,stroke:#4a148c
    class TAPP qa
```

La flecha punteada de `rollback.yml` indica que cualquier tag puede
redesplegarse en cualquier Environment — incluso un `X.Y.Z` antiguo en `prod`,
previa aprobación.

## Puertos, probes y Feature Flag

Cada Environment expone los mismos tres probes en su puerto:

```sh
curl --fail http://localhost:8001/healthz | jq .  # dev
curl --fail http://localhost:8001/readyz  | jq .
curl --fail http://localhost:8001/version | jq .  # {"version":"<SHA8>"}

curl --fail http://localhost:8002/version | jq .  # staging
curl --fail http://localhost:8003/version | jq .  # prod
```

Cada Environment necesita su `POSTGRES_PASSWORD` y puede usar un valor diferente; difieren en `FEATURE_LABEL_FILTERING` (`true` en `dev`/`staging`, `false` en `prod`).
La factory `app/app/__init__.py` lee `FEATURE_LABEL_FILTERING` mediante el parser de `app/app/config.py` y se prueba en `app/tests/test_probes_version_flag.py`
— ver [`docs/secrets-and-config.md`](secrets-and-config.md).

## Glosario rápido

Ver `CONTEXT.md` para las definiciones canónicas; aquí los términos en uso:

- **Environment** — destino de despliegue (`dev`/`staging`/`prod`). Cada uno
  es un proyecto Compose aislado.
- **Release Tag** — `X.Y.Z-snapshot` (staging, móvil) o `X.Y.Z` (prod,
  inmutable por convención). En CD, es `APP_VERSION` y forma parte de `IMAGE_TAG=tag@digest`.
- **Edge Build** — imagen de `push` a `main`, tag `SHA8`, sin Release Tag.
- **Feature Flag** — `FEATURE_LABEL_FILTERING` por Environment sin
  reconstruir.

Siguientes pasos: [`docs/release-process.md`](release-process.md) detalla
cómo promover un artefacto por estos entornos y
[`docs/pipeline.md`](pipeline.md) cómo el pipeline lo construye.
