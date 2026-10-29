# hiss

Un gestor de issues mínimo y autoalojable (Flask + Postgres + API REST + CLI), construido como material docente para un curso de CI/CD con GitHub Actions y Docker. Todo el código y los identificadores están en inglés; toda la documentación en español.

[![CI](https://github.com/mvieitesr/hiss/actions/workflows/ci.yml/badge.svg)](https://github.com/mvieitesr/hiss/actions/workflows/ci.yml)

> Ver [`CONTEXT.md`](CONTEXT.md) para el glosario de dominio (`Project`, `Issue`, `Label`, `Comment`, `Environment`, `Release Tag`, `Feature Flag`, `Edge Build`).

## Arquitectura

```mermaid
flowchart TB
    GH["GitHub Actions<br/>ci.yml (ubuntu-latest)<br/>cd-dev / cd-staging / cd-prod<br/>_build-push.yml (reusable)<br/>rollback.yml (workflow_dispatch)"]
    GH -->|"build SHA8 / promover por digest"| REG["GHCR del dueño<br/>ghcr.io/&lt;dueño&gt;/hiss"]

    REG --> DEV["hiss-dev :8001<br/>app (8000 interno) + db postgres:17-alpine<br/>COMPOSE_PROJECT_NAME=hiss-dev"]
    REG --> STAG["hiss-staging :8002<br/>app + db postgres:17-alpine<br/>hiss-staging"]
    REG --> PROD["hiss-prod :8003<br/>app + db postgres:17-alpine<br/>hiss-prod + gate prod"]

    DEV --> DBD[("pgdata dev<br/>volumen")]
    STAG --> DBS[("pgdata staging")]
    PROD --> DBP[("pgdata prod")]

    REG -.->|"tags BLUE_TAG / GREEN_TAG"| BG["deploy/blue-green :9000<br/>migrate + blue + green + proxy nginx:1.27-alpine<br/>postgres:16-alpine compartido<br/>COMPOSE_PROJECT_NAME=hiss-blue-green"]

    DEV --- NET["red interna db:5432<br/>5432 no publicado en host"]
    STAG --- NET
    PROD --- NET
    BG --- NET2["red blue-green db:5432"]

    classDef env fill:#e3f2fd,stroke:#1565c0
    class DEV,STAG,PROD env
    classDef demo fill:#fff3e0,stroke:#ef6c00
    class BG demo
```

Cada Environment (`dev` `:8001`, `staging` `:8002`, `prod` `:8003`) usa el mismo `deploy/compose.yml` con distinto `--env-file`. El servidor Flask de desarrollo corre en `8000` (`flask --app app.app:create_app run --port 8000`) y no colisiona con ningún Environment. Compose no publica `5432` en el host.

## Inicio rápido en 5 minutos

Requisitos: runner autoalojado en `Idle`, Environments y paquete preparados (ver [`docs/setup.md`](docs/setup.md)). Antes de cortar un Release Tag, espera al CI de `push` a `main` y a que `cd-dev` publique la imagen SHA8 de ese mismo commit. Usa tu repo en los comandos `gh`.

```sh
# 0. Verifica el runner (debe mostrar Idle en Settings → Actions → Runners)
gh api /repos/mvieitesr/hiss/actions/runners --jq '.runners[] | "\(.name) \(.status)"'

# 1. Runner ya escuchando (./run.sh o svc.sh start) — si no, levántalo:
# cd ~/actions-runner && ./run.sh

# 2. Corta un snapshot desde main y observa staging en :8002
git checkout main && git pull --ff-only origin main
git tag 0.2.0-snapshot && git push origin 0.2.0-snapshot
gh run list --workflow cd-staging.yml --limit 3
gh run watch --exit-status
curl --fail http://localhost:8002/healthz | jq .
curl --fail http://localhost:8002/version | jq .  # {"version":"0.2.0-snapshot"}

# 3. Promueve a release inmutable y aprueba prod en :8003
git tag 0.2.0 0.2.0-snapshot && git push origin 0.2.0
gh run list --workflow cd-prod.yml --limit 3
# Abre Actions → CD — prod → Review pending deployments → Approve
gh run watch --exit-status
curl --fail http://localhost:8003/version | jq .  # {"version":"0.2.0"}

# 4. Verifica dev en :8001 (CI verde en main dispara cd-dev.yml con SHA8)
git commit --allow-empty -m "chore: quickstart check" && git push origin main
gh run list --workflow ci.yml --limit 3
gh run watch --exit-status   # espera a CI; CD no arranca si CI falla
gh run list --workflow cd-dev.yml --limit 3
gh run watch --exit-status
curl --fail http://localhost:8001/version | jq .  # {"version":"<SHA8>"}

# 5. Observabilidad básica: Compose también necesita estas variables en ps/logs
export POSTGRES_PASSWORD='elige-el-secreto-local'
export IMAGE_TAG="$(git rev-parse --short=8 HEAD)" APP_VERSION="$(git rev-parse --short=8 HEAD)"
docker compose --env-file deploy/dev.env -p hiss-dev ps
docker compose --env-file deploy/dev.env -p hiss-dev logs -f app
curl --fail http://localhost:8001/readyz | jq .
```

Para desarrollo local sin Compose, prepara PostgreSQL externo con una base `hiss`, usuario `postgres` y contraseña conocida; el Postgres de Compose no publica su puerto. Desde la raíz, ajusta la URL a tus credenciales y migra **antes** de iniciar Flask:

```sh
python -m venv .venv && source .venv/bin/activate
pip install -r app/requirements.txt
export DATABASE_URL='postgresql://postgres:postgres@localhost:5432/hiss'
alembic -c app/alembic.ini upgrade head
flask --app app.app:create_app run --port 8000
```

## API

La API usa `/api/v1`. Los cuerpos de creación y edición deben ser objetos JSON con tipos válidos; ante valores inválidos responde `400` con `error` y `message`. Después de recortar espacios, los límites son 50 caracteres para `Project.key`, 200 para `Project.name`, 300 para el título de `Issue` y 100 para `Label.name`. La key y el nombre de Label no pueden contener `/` ni ser exactamente `.` o `..`; otros caracteres de ruta deben codificarse como segmento URL (la CLI lo hace).

## Documentación

Índice completo — cada documento es autocontenido y enlaza a los demás:

| Documento | Qué cubre |
| --- | --- |
| [`docs/setup.md`](docs/setup.md) | Configuración del repo, CI en `ci.yml`, protección de `main`, runner autoalojado paso a paso (macOS/Linux, `self-hosted`, `post-registration token` vía `gh api`), Environments `dev`/`staging`/`prod` con `POSTGRES_PASSWORD` y GHCR público |
| [`docs/pipeline.md`](docs/pipeline.md) | Pipeline completo: `push`→`ci.yml` (`changes`/`lint-pipeline`/`lint`/`test-app` con `postgres:17-alpine`/`test-cli`/`build`) → `cd-dev.yml` (`SHA8`→`:8001`)/`cd-staging.yml` (`snapshot`→`:8002`)/`cd-prod.yml` (`X.Y.Z`→`:8003` gate) vía `_build-push.yml` (`workflow_call`), smoke tests `curl`+`jq --arg expected` |
| [`docs/environments.md`](docs/environments.md) | 4 entornos del temario → 3 despliegues `hiss-dev:8001`/`hiss-staging:8002`/`hiss-prod:8003` + QA efímero (`test-app` service container `postgres:17-alpine`), tablas `IMAGE_TAG`/`APP_VERSION`/`FEATURE_LABEL_FILTERING`, `COMPOSE_PROJECT_NAME` |
| [`docs/release-process.md`](docs/release-process.md) | Runbook `X.Y.Z-snapshot` móvil (`git tag -d`+`push --delete`+`git tag X.Y.Z-snapshot && git push`), endurecer, `X.Y.Z` inmutable, aprobar `prod`, `rollback.yml` |
| [`docs/deployment-strategies.md`](docs/deployment-strategies.md) | Recreate / Rolling / Blue-Green / Canary con Mermaid, demo `deploy/blue-green/` en `:9000` (`switch.sh` `status`/`switch`/`deploy`/`rollback`, `curl :9000/version`), migración `0002` aditiva |
| [`docs/secrets-and-config.md`](docs/secrets-and-config.md) | 12-factor, `deploy/*.env` versionados vs `POSTGRES_PASSWORD` inyectada (`secrets.POSTGRES_PASSWORD`), `FEATURE_LABEL_FILTERING` (`true`/`true`/`false`, `app/app/config.py`, `test_probes_version_flag.py`) |

**Material para el profesor — `docs/teacher/` (teacher-only, no es parte del recorrido del alumno):**

- [`docs/teacher/course-map.md`](docs/teacher/course-map.md) — mapa temático de ficheros/workflows/demos (no trazabilidad curricular oficial)
- [`docs/teacher/workflow-refactor-lesson.md`](docs/teacher/workflow-refactor-lesson.md) — lección `workflows-duplicated` → `_build-push.yml` (`git show`, `git diff`)
- [`docs/teacher/blue-green-guide.md`](docs/teacher/blue-green-guide.md) — guía para ejecutar la demo en clase (`demo-check.sh`, `BLUE_GREEN_PORT=9000`, `down -v`)

**Decisiones de arquitectura — `docs/adr/`:**

- [`docs/adr/0001-self-hosted-runner-environments.md`](docs/adr/0001-self-hosted-runner-environments.md) — runner `self-hosted` + Environments como CD (rechazadas: Watchtower, SSH, cloud)
- [`docs/adr/0002-sin-autenticacion.md`](docs/adr/0002-sin-autenticacion.md) — sin autenticación por alcance docente (rechazadas: auth completa, API tokens)

---

## Integración continua

GitHub Actions ejecuta los checks de lint, tests y construcción de imagen
descritos en [`docs/setup.md`](docs/setup.md). Configura manualmente la
protección de la rama `main` después de la primera ejecución del workflow para
que un resultado rojo de CI bloquee los merges.

## Despliegue con Docker Compose

Para construir y publicar manualmente una imagen en el GHCR de tu fork, ver [Local Stack](docs/environments.md#local-stack-manual-con-ghcr-del-fork).

La imagen de la aplicación se referencia como `${IMAGE}:${IMAGE_TAG}`. Cada
archivo `deploy/*.env` fija `IMAGE=ghcr.io/mvieitesr/hiss` por defecto; puedes
sobreescribir `IMAGE` desde el shell para usar otro registro. Los workflows
usan `ghcr.io/<dueño-del-repo-en-minúsculas>/hiss`, también en forks.
El paquete de GHCR debe estar configurado como **público** para que los hosts de
despliegue y los runners puedan hacer pull anónimo sin un token de GitHub. Esto
también significa que cualquiera puede descargar la imagen; la visibilidad
pública no expone las credenciales de Postgres.

El responsable del repositorio publicará los tags de ejemplo `0.1.0`, `0.1.1` y `0.1.0-snapshot` de `mvieitesr/hiss` antes de la práctica; usa un SHA8 publicado para dev. Para un fork propio, publica las imágenes allí y exporta `IMAGE`.

Los archivos `deploy/*.env` están versionados y contienen sólo configuración no
secreta. Los valores predeterminados seleccionan tags distintos; los CD promocionan el mismo digest cuando los Release Tags apuntan al mismo commit:

| Environment | Puerto publicado | `IMAGE_TAG` / `APP_VERSION` | `FEATURE_LABEL_FILTERING` | Proyecto Compose |
| --- | ---: | --- | --- | --- |
| dev | 8001 | vacíos; inyectar SHA de 8 caracteres en ambos | `true` | `hiss-dev` |
| staging | 8002 | `0.1.0-snapshot` | `true` | `hiss-staging` |
| prod | 8003 | `0.1.0` | `false` | `hiss-prod` |

En CD, `IMAGE_TAG` recibe `tag@digest` y `APP_VERSION` solo el tag; son variables independientes. `/version` devuelve la cadena configurada, no prueba por sí sola el digest ni el SHA de la imagen. Los nombres `hiss-dev`, `hiss-staging` y
`hiss-prod` permiten que las tres Environments coexistan en el mismo host.

### Credencial de Postgres

`POSTGRES_PASSWORD` **nunca se versiona** ni aparece en los archivos de
Environment. En local, inyéctala desde el entorno del proceso y despliega desde
la raíz del repositorio:

```sh
export POSTGRES_PASSWORD='elige-un-secreto-local'
export IMAGE_TAG="$(git rev-parse --short=8 HEAD)" APP_VERSION="$(git rev-parse --short=8 HEAD)"
# Usa un SHA8 publicado en el GHCR elegido; APP_TAG no es una variable de Compose.
docker compose --env-file deploy/dev.env -p hiss-dev up -d
```

Para las otras Environments:

```sh
export POSTGRES_PASSWORD='elige-un-secreto-local'
unset IMAGE_TAG APP_VERSION  # usa los valores de cada env-file
docker compose --env-file deploy/staging.env -p hiss-staging up -d
docker compose --env-file deploy/prod.env -p hiss-prod up -d
```

Las variables exportadas del shell tienen precedencia sobre los env-files; vuelve a exportar las de dev para sus ejemplos posteriores y elimínalas para usar los valores de staging o prod (`unset IMAGE_TAG APP_VERSION`). Si falta la contraseña, el tag o la versión, Compose falla en lugar de arrancar. En CI/CD, el
workflow debe inyectar el mismo valor desde el secreto del GitHub Environment,
sin escribirlo en el repositorio ni en `deploy/*.env`.

La definición canónica también puede invocarse explícitamente con
`-f deploy/compose.yml`; vuelve a exportar `IMAGE_TAG` y `APP_VERSION` con el SHA8 publicado antes de los comandos de dev:

```sh
export IMAGE_TAG="$(git rev-parse --short=8 HEAD)" APP_VERSION="$(git rev-parse --short=8 HEAD)"
docker compose -f deploy/compose.yml --env-file deploy/dev.env -p hiss-dev up -d
```

### Red, probes y logs

La base de datos sólo es accesible dentro de la red de Compose mediante el nombre
DNS `db` y el puerto interno 5432; **no se publica 5432 en el host**. Sólo se
publica la aplicación, en 8001 (dev), 8002 (staging) o 8003 (prod), evitando
colisiones con un Postgres local o con el servidor Flask de desarrollo en 8000.

Al iniciar el contenedor de la aplicación, el entrypoint ejecuta
`alembic upgrade head` y después inicia Gunicorn. Compose espera a que Postgres
esté saludable y mantiene probes para liveness, readiness y versión:

```sh
docker compose --env-file deploy/dev.env -p hiss-dev ps
docker compose --env-file deploy/dev.env -p hiss-dev logs -f app

# Desde el host de dev:
curl --fail http://localhost:8001/healthz
curl --fail http://localhost:8001/readyz
curl --fail http://localhost:8001/version
```

Estos comandos (`docker compose ps` y `docker compose logs`) son la
monitorización básica del despliegue. Para detener un Environment sin borrar sus
datos persistentes usa `down`; añade `-v` sólo cuando también quieras eliminar
su volumen de Postgres:

```sh
docker compose --env-file deploy/dev.env -p hiss-dev down
```
