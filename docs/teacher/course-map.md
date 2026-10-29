# Mapa temático — módulo 5168

> **Orientado al profesor — teacher-only.** Este documento no forma parte del recorrido
> del estudiante, aunque es legible para cualquiera. Su objetivo es que
> puedas relacionar temas docentes del módulo 5168 con artefactos concretos. Este mapa es orientativo: no reproduce ni verifica los resultados y criterios oficiales; el profesor debe contrastarlo con el currículo vigente antes de usarlo como cobertura.

## Cómo usar este mapa

Cada bloque agrupa temas orientativos y, para cada uno, el fichero,
workflow, job o demo que lo enseña. Todas las referencias son
verificables con `grep` o abriendo el fichero en el `main` actual. Si un
bullet no tiene artefacto, se registra como hueco y se resuelve con el
profesor — no se improvisa.

Convención de referencias: `ruta:job` o `ruta:línea aproximada`. Las líneas
exactas pueden desplazarse; el `grep` indicado lo localiza.

---

## Bloque A — Fundamentos de integración y entrega continua

| Bullet del temario | Artefacto que lo enseña | Verificación |
| --- | --- | --- |
| **CD fundamentals — integración, entrega y despliegue como pipeline** | `docs/pipeline.md` (vista general CI vs CD, patrón `prepare→build→deploy→smoke-test`) + `docs/environments.md` (dónde se despliega) | `grep -n "prepare.*build.*deploy" docs/pipeline.md` |
| **Delivery vs Deployment — gating manual** | `docs/pipeline.md` sección *Delivery vs Deployment* (sequenceDiagram `dev`/`staging` auto vs `prod` gate) + `docs/release-process.md` (aprobar `prod` en UI) | `grep -n "Delivery vs Deployment\|Required reviewers" docs/pipeline.md` |
| **Environments — Development, Testing/QA, Staging, Production** | `docs/environments.md` (tabla 4 entornos → 3 despliegues `hiss-dev:8001`/`hiss-staging:8002`/`hiss-prod:8003` + QA efímero) + `deploy/compose.yml` (`name: ${COMPOSE_PROJECT_NAME:-hiss-dev}`) + `deploy/*.env` | `grep -n "Testing / QA\|hiss-dev\|hiss-staging\|hiss-prod" docs/environments.md` |
| **Artifact lifecycle — construir una vez, desplegar en cualquier sitio** | `deploy/compose.yml` (`image: ${IMAGE}:${IMAGE_TAG}` + `build: context: ../app`) + `.github/workflows/_build-push.yml` (construcción SHA8 y promoción de digest al GHCR del dueño) + `deploy/*.env` | `grep -En 'source_tag\|digest\|GITHUB_REPOSITORY_OWNER' .github/workflows/_build-push.yml` |
| **Triggers — qué dispara cada workflow** | `docs/pipeline.md` tabla de triggers (CI verde en `main` → `cd-dev.yml` via `workflow_run`, `push` tag `X.Y.Z-snapshot` → `cd-staging.yml` con `ci-gate`, `X.Y.Z` → `cd-prod.yml` con `ci-gate`, `workflow_dispatch` → `rollback.yml`) + `.github/workflows/ci.yml:on: pull_request` vs `.github/workflows/cd-dev.yml:on: workflow_run` | `grep -n "on:" .github/workflows/cd-dev.yml` + `grep -n "on:" .github/workflows/cd-staging.yml` + `grep -n "on:" .github/workflows/cd-prod.yml` |
| **Immutability — snapshot móvil vs release inmutable** | `docs/release-process.md` (sección *Mutabilidad*, `git tag -d` + `git push --delete` para `snapshot` vs nunca reescribir `X.Y.Z`) + `docs/setup.md:Mutabilidad de los tags` | `grep -n "snapshot.*móvil\|X.Y.Z.*inmutable" docs/release-process.md` |

**Jobs clave del bloque A:** `cd-dev.yml:prepare` (`head_sha` a 8 caracteres, solo si CI fue `success` en `push` a `main`), `cd-staging.yml:ci-gate` + `prepare` (`github.ref_name`), `cd-prod.yml:environment: prod` (gate).

---

## Bloque B — Pipeline as code, gestión de artefactos y secretos

| Bullet del temario | Artefacto | Verificación |
| --- | --- | --- |
| **Pipeline as code — workflows en YAML versionados** | `.github/workflows/ci.yml` (7 jobs en `ubuntu-latest`), `.github/workflows/cd-dev.yml`/`cd-staging.yml`/`cd-prod.yml`/`rollback.yml` (self-hosted), `.github/workflows/_build-push.yml` (reusable) | `ls .github/workflows/*.yml` + `cat .github/workflows/ci.yml` |
| **Jobs — lint, test, build como grafo de dependencias** | `ci.yml:jobs: lint-pipeline` (actionlint + Compose, siempre); `changes` (`dorny/paths-filter@v3` con `app`/`cli`/`shared`) → `lint` (`ruff==0.9.10`), `lint-docker` (`hadolint`), `test-app` (`postgres:17-alpine` + `alembic upgrade head` + `pytest app/tests`), `test-cli`, `build` (`docker build -f app/Dockerfile app/`) | `grep -n "needs: changes\|dorny/paths-filter\|hadolint\|postgres:17-alpine" .github/workflows/ci.yml` |
| **GHCR tagging y promoción por digest** | `_build-push.yml:jobs:build` deriva `IMAGE` del dueño; construye o promociona un digest existente según `source_tag` + `docs/secrets-and-config.md` | `grep -En 'GITHUB_REPOSITORY_OWNER\|source_tag\|digest' .github/workflows/_build-push.yml` |
| **Secrets — `POSTGRES_PASSWORD` nunca versionada** | `deploy/*.env` (sin `POSTGRES_PASSWORD`), `deploy/compose.yml` (`POSTGRES_PASSWORD:?must be set`, `DATABASE_URL: postgresql://...@db:5432/`), `cd-*.yml:env: POSTGRES_PASSWORD: ${{ secrets.POSTGRES_PASSWORD }}`, `docs/secrets-and-config.md` (12-factor) + `docs/setup.md:GitHub Environments` | `grep -n '^POSTGRES_PASSWORD=' deploy/*.env \|\| echo "ok"` + `grep -n "secrets.POSTGRES_PASSWORD" .github/workflows/cd-dev.yml` |

**Check rápido del bloque B en clase:**

```sh
POSTGRES_PASSWORD=dummy IMAGE_TAG=deadbeef APP_VERSION=deadbeef docker compose --env-file deploy/dev.env -p hiss-docs-check config -q && echo "compose ok"
grep -n '^POSTGRES_PASSWORD=' deploy/*.env && echo "fail" || echo "ok: sin secreto versionado"
gh secret list --env dev | grep POSTGRES_PASSWORD
```

---

## Bloque C — Estrategias de despliegue y migraciones

| Bullet del temario | Artefacto | Verificación |
| --- | --- | --- |
| **Recreate** | `docs/deployment-strategies.md:Recreate` + `deploy/compose.yml` (`docker compose up -d` con downtime visible) | `grep -n "Recreate" docs/deployment-strategies.md` |
| **Rolling** | `docs/deployment-strategies.md:Rolling` (teoría, `K8s RollingUpdate`, `maxUnavailable`/`maxSurge`) — sin demo Compose por necesitar orquestador | `grep -n "Rolling" docs/deployment-strategies.md` |
| **Blue-Green** | `deploy/blue-green/compose.yml` (5 servicios: `db` `postgres:16-alpine`, `migrate`, `blue`/`green` `ghcr.io/mvieitesr/hiss:${BLUE_TAG}`, `proxy` `nginx:1.27-alpine` en `:9000`), `deploy/blue-green/switch.sh` (`status`/`switch`/`deploy`/`rollback`), `deploy/blue-green/nginx.conf.template` (`envsubst '${ACTIVE_SLOT}'`), `deploy/blue-green/README.es.md` (sequenceDiagram cutover), `docs/deployment-strategies.md:Blue-Green` | `cat deploy/blue-green/compose.yml \| grep -E "blue:|green:|proxy:"` + `./deploy/blue-green/switch.sh help` |
| **Canary** | `docs/deployment-strategies.md:Canary` (teoría, pesos 90/10, métricas y mesh) | `grep -n "Canary" docs/deployment-strategies.md` |
| **Feature Flags** | `deploy/*.env` (`FEATURE_LABEL_FILTERING=true` en `dev`/`staging`, `false` en `prod`), `app/app/__init__.py:create_app` + `app/app/config.py:_parse_feature_flag`, `app/tests/test_probes_version_flag.py:test_label_filter_when_flag_off_returns_400`, `docs/secrets-and-config.md:Feature Flag` | `grep -n FEATURE_LABEL_FILTERING deploy/*.env app/app/__init__.py` |
| **Backward-compatible migrations** | `app/alembic/versions/0002_create_labels_issue_labels.py` (puramente aditiva: `CREATE TABLE labels` + `issue_labels`, sin `ALTER`), `docs/deployment-strategies.md:Migraciones` (expand & contract, DB compartida en blue-green) | `cat app/alembic/versions/0002_create_labels_issue_labels.py \| grep -E "create_table\|create_index"` |

**Demo del bloque C en clase:** primero el responsable del repositorio publica `0.1.0` y `0.1.1` en `ghcr.io/mvieitesr/hiss`; alternativamente, usa imágenes propias publicadas y exporta `IMAGE`. `export POSTGRES_PASSWORD=changeme` → `docker compose -f deploy/blue-green/compose.yml --env-file deploy/blue-green/.env.example up -d --wait --wait-timeout 60` → `./deploy/blue-green/switch.sh switch green` → `curl -s http://localhost:9000/version` (ver `docs/teacher/blue-green-guide.md`).

---

## Bloque D — Probes, smoke tests, rollback y supervisión

| Bullet del temario | Artefacto | Verificación |
| --- | --- | --- |
| **Probes — liveness, readiness y versión** | `app/app/api/probes.py:register_probes` (`GET /healthz` sin DB, `GET /readyz` con `SELECT 1`, `GET /version` con `APP_VERSION`), `deploy/compose.yml:healthcheck` (`python -c 'urllib.request.urlopen(\"http://localhost:8000/healthz\")'`), `deploy/blue-green/compose.yml:healthcheck` idéntico | `grep -n "/healthz\|/readyz\|/version" app/app/api/probes.py` |
| **Smoke tests — verificación post-despliegue** | `cd-dev.yml:smoke-test` (`BASE_URL=http://localhost:8001`, `curl --fail --max-time 10 --retry 10 ... /healthz /readyz /version \| jq --exit-status --arg expected`) + `cd-staging.yml` (`:8002`) + `cd-prod.yml` (`:8003`) + `rollback.yml:smoke-test` con selección de puerto | `grep -n "smoke-test\|BASE_URL\|/healthz" .github/workflows/cd-dev.yml` |
| **Rollback — volver a una versión anterior** | `rollback.yml` (`workflow_dispatch` con `environment: dev\|staging\|prod` y `tag: string`, `case` para `env_file`/`project`, `pull` + `up -d`, gate `prod` con aprobación) + `docs/release-process.md:Rollback` + `deploy/blue-green/switch.sh rollback` (proxy) | `grep -n "workflow_dispatch\|TARGET_ENV" .github/workflows/rollback.yml` |
| **Monitoring — teoría y práctica honesta** | `docs/deployment-strategies.md:Observabilidad` (`docker compose ps` estados `healthy`, `docker compose logs -f app`, dashboard de Environments como poor man's monitoring) + `docs/secrets-and-config.md` + `README.md:Red, probes y logs` | `grep -n "docker compose ps\|docker compose logs" docs/deployment-strategies.md` |
| **Monitoring theory — Prometheus/Grafana/Loki** | `docs/deployment-strategies.md` nota teórica (métricas, dashboards, logs, sin hands-on por alcance) | `grep -n "Prometheus\|Grafana\|Loki" docs/deployment-strategies.md` |
| **GitOps theory — ArgoCD** | `docs/deployment-strategies.md` nota teórica (reconciliación declarativa, sin infra extra) | `grep -n "ArgoCD\|GitOps" docs/deployment-strategies.md` |

**Comandos de verificación del bloque D en clase:**

```sh
export POSTGRES_PASSWORD='elige-un-secreto-local'
export IMAGE_TAG="$(git rev-parse --short=8 HEAD)" APP_VERSION="$(git rev-parse --short=8 HEAD)"
curl --fail http://localhost:8001/healthz | jq .
curl --fail http://localhost:8001/readyz  | jq .
curl --fail http://localhost:8001/version | jq .
docker compose --env-file deploy/dev.env -p hiss-dev ps
docker compose --env-file deploy/dev.env -p hiss-dev logs -f app
gh workflow run rollback.yml -f environment=prod -f tag=0.1.0
```

---

## Cobertura y huecos

Los temas de esta tabla tienen artefacto asignado, pero falta contrastar los RA y criterios oficiales. Entre los posibles huecos están cálculo de costes, BDD, orquestación, análisis estático, almacenaje de artefactos y Dockerfile. Rolling y Canary requieren orquestador; Prometheus/Grafana/Loki y GitOps/ArgoCD solo se explican, no se despliegan. El profesor debe decidir la cobertura y las actividades antes de añadir infraestructura.

## Referencias rápidas por fichero

- `docs/pipeline.md` — pipeline CI/CD completo con Mermaid
- `docs/environments.md` — 4 entornos → 3 despliegues + QA efímero
- `docs/release-process.md` — runbook `snapshot` → `X.Y.Z` + rollback
- `docs/secrets-and-config.md` — 12-factor, `*.env` vs secretos, Feature Flag
- `docs/deployment-strategies.md` — Recreate/Rolling/Blue-Green/Canary + 0002
- `deploy/blue-green/` — demo blue-green autocontenida
- `app/alembic/versions/0002_create_labels_issue_labels.py` — migración aditiva
- `app/app/api/probes.py` — probes, `app/app/__init__.py` y `app/app/config.py` — flags
