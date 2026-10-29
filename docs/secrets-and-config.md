# Secretos y configuración

Este documento explica cómo hiss separa configuración y secretos
siguiendo el principio 12-factor, qué ficheros están versionados y
cuáles nunca deben versionarse, y cómo la Feature Flag permite cambiar
comportamiento por Environment sin reconstruir la imagen.

## Principio 12-factor

La app no lee ficheros de configuración por entorno. `create_app` en `app/app/__init__.py` lee las variables al crear cada app y usa `_parse_feature_flag` de `app/app/config.py` para interpretar la flag; convierte la URL de PostgreSQL para el driver psycopg. Así los tests pueden mutar flags sin recargar el proceso. Los valores por defecto permiten
arrancar sin entorno completo (`sqlite:///:memory:` para tests,
`APP_VERSION=dev`).

## `deploy/*.env` — configuración versionada no secreta

Tres ficheros idénticos en estructura, distintos en cinco valores.
Están en Git y se pueden auditar:

| Variable | `deploy/dev.env` | `deploy/staging.env` | `deploy/prod.env` |
| --- | --- | --- | --- |
| `COMPOSE_PROJECT_NAME` | `hiss-dev` | `hiss-staging` | `hiss-prod` |
| `IMAGE` | `ghcr.io/mvieitesr/hiss` | `ghcr.io/mvieitesr/hiss` | `ghcr.io/mvieitesr/hiss` |
| `IMAGE_TAG` | vacío (inyectar SHA8) | `0.1.0-snapshot` | `0.1.0` |
| `APP_VERSION` | vacío (inyectar SHA8) | `0.1.0-snapshot` | `0.1.0` |
| `APP_PORT` | `8001` | `8002` | `8003` |
| `FEATURE_LABEL_FILTERING` | `true` | `true` | `false` |
| `POSTGRES_DB` | `hiss` | `hiss` | `hiss` |
| `POSTGRES_USER` | `postgres` | `postgres` | `postgres` |

Todos declaran:

```
# Hiss — Environment config (committed, non-secret)
# DB password is injected at deploy time — never committed.
```

`IMAGE` es parametrizable: puedes sobreescribirlo en el shell para
validar otro registro sin editar el repo:

```sh
POSTGRES_PASSWORD=dummy IMAGE_TAG=deadbeef APP_VERSION=deadbeef IMAGE=ghcr.io/otro/hiss \
  docker compose -f deploy/compose.yml --env-file deploy/dev.env -p hiss-docs-check config --images
```

Las variables son independientes: en dev ambas se inyectan con SHA8; en CD `IMAGE_TAG` incluye `tag@digest` y `APP_VERSION` solo el tag. `APP_TAG` no se usa. `/version` devuelve `APP_VERSION`, no demuestra el digest. Los workflows derivan `IMAGE` del dueño del repositorio en minúsculas; el `.env` solo es el valor manual por defecto. Los tags de ejemplo `0.1.0`, `0.1.1` y `0.1.0-snapshot` de `mvieitesr/hiss` los publicará el responsable del repositorio antes de la práctica.

Comprueba que ningún `.env` contiene secretos:

```sh
grep -n '^POSTGRES_PASSWORD=' deploy/*.env || echo "ok: ningún secreto versionado"
cat deploy/dev.env
cat deploy/staging.env
cat deploy/prod.env
```

## `POSTGRES_PASSWORD` — secreto nunca versionado

`POSTGRES_PASSWORD` se declara en `deploy/compose.yml` con validación
estricta:

```yaml
services:
  db:
    environment:
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:?must be set}
  app:
    environment:
      DATABASE_URL: postgresql://${POSTGRES_USER:-postgres}:${POSTGRES_PASSWORD:?must be set}@db:5432/${POSTGRES_DB:-hiss}
```

Si falta, Compose falla en seco en lugar de arrancar con una contraseña
por defecto. La base de datos nunca publica `5432` en el host — solo es
accesible como `db:5432` dentro de la red de Compose.

### En local

Inyecta la contraseña desde el entorno del proceso:

```sh
export POSTGRES_PASSWORD='elige-un-secreto-local'
export IMAGE_TAG="$(git rev-parse --short=8 HEAD)" APP_VERSION="$(git rev-parse --short=8 HEAD)" # SHA8 publicado
docker compose --env-file deploy/dev.env -p hiss-dev up -d
docker compose --env-file deploy/dev.env -p hiss-dev ps

# Para staging/prod usa sus valores del env-file
unset IMAGE_TAG APP_VERSION
docker compose -f deploy/compose.yml --env-file deploy/staging.env -p hiss-staging up -d
docker compose -f deploy/compose.yml --env-file deploy/prod.env -p hiss-prod up -d

# Restablece valores de dev antes de cualquier comando Compose de dev
export IMAGE_TAG="$(git rev-parse --short=8 HEAD)" APP_VERSION="$(git rev-parse --short=8 HEAD)"
# Readiness prueba la conexión sin imprimir la contraseña
curl --fail http://localhost:8001/readyz | jq .  # hace SELECT 1 real con la contraseña
```

Para detener sin borrar datos:

```sh
docker compose --env-file deploy/dev.env -p hiss-dev down      # mantiene pgdata
docker compose --env-file deploy/dev.env -p hiss-dev down -v   # borra volumen de ese Environment
```

### En CI/CD

Cada `cd-*.yml` y `rollback.yml` inyecta el secreto desde el GitHub
Environment:

```yaml
deploy:
  runs-on: [self-hosted]
  environment: dev
  env:
    DEPLOY_TAG: ${{ needs.prepare.outputs.tag }}
    IMAGE: ${{ needs.build.outputs.image }}
    DIGEST: ${{ needs.build.outputs.digest }}
    POSTGRES_PASSWORD: ${{ secrets.POSTGRES_PASSWORD }}
  steps:
    - run: |
        POSTGRES_PASSWORD="$POSTGRES_PASSWORD" IMAGE_TAG="$DEPLOY_TAG@$DIGEST" APP_VERSION="$DEPLOY_TAG" \
          docker compose -f deploy/compose.yml --env-file deploy/dev.env -p hiss-dev pull
        POSTGRES_PASSWORD="$POSTGRES_PASSWORD" IMAGE_TAG="$DEPLOY_TAG@$DIGEST" APP_VERSION="$DEPLOY_TAG" \
          docker compose -f deploy/compose.yml --env-file deploy/dev.env -p hiss-dev up -d --no-build --pull never
```

Configura el secreto por Environment en **Settings → Environments → dev/staging/prod →
Environment secrets → POSTGRES_PASSWORD** (ver `docs/setup.md`). `prod`
además tiene `Required reviewers` — el despliegue pausa hasta aprobación.

El secreto no se escribe en `deploy/*.env`. Evita mostrar `docker compose config` o `inspect` con secretos reales: contienen valores interpolados. Un paquete privado requiere autenticación de Docker en el runner; un paquete público permite pull anónimo (ver `docs/setup.md`).

## Feature Flag — `FEATURE_LABEL_FILTERING`

Una variable de entorno que activa o desactiva el filtrado por etiqueta
sin cambiar la imagen.

| Environment | `FEATURE_LABEL_FILTERING` | Efecto |
| --- | --- | --- |
| `dev` | `true` | filtrado por `?label=bug` activo |
| `staging` | `true` | igual que `dev` — pruebas de la feature |
| `prod` | `false` | filtrado deshabilitado — `GET /projects/:key/issues?label=...` devuelve `400` |

Lectura en `app/app/config.py`:

```python
def _parse_feature_flag(value: str | None) -> bool:
    if value is None:
        return True
    lower = value.strip().lower()
    if lower in ("true", "1", "yes", "on"):
        return True
    if lower in ("false", "0", "no", "off"):
        return False
    return True  # fallback conservador
```

Pruebas en `app/tests/test_probes_version_flag.py`:

- `test_label_filter_when_flag_on_returns_filtered` — con flag `true` filtra por label.
- `test_label_filter_when_flag_off_returns_400` — con `FEATURE_LABEL_FILTERING=false` la query `?label=bug` devuelve `400` con mensaje `disabled` o `flag`.

Si la API devuelve `feature_disabled`, la SPA retira el filtro de Label, conserva los demás filtros y recarga mostrando un aviso. Para probar localmente, crea `PRJ` en cada base independiente (o usa otra key si ya existe):

```sh
# Con filtrado activo (dev/staging)
export POSTGRES_PASSWORD='elige-un-secreto-local'
export IMAGE_TAG="$(git rev-parse --short=8 HEAD)" APP_VERSION="$(git rev-parse --short=8 HEAD)" # SHA8 publicado
docker compose --env-file deploy/dev.env -p hiss-dev up -d --wait --wait-timeout 60
curl -fsS -X POST -H 'Content-Type: application/json' -d '{"key":"PRJ","name":"Proyecto"}' http://localhost:8001/api/v1/projects
curl -s http://localhost:8001/api/v1/projects/PRJ/issues?label=bug | jq .

# Con filtrado desactivado (prod)
unset IMAGE_TAG APP_VERSION
docker compose --env-file deploy/prod.env -p hiss-prod up -d --wait --wait-timeout 60
curl -fsS -X POST -H 'Content-Type: application/json' -d '{"key":"PRJ","name":"Proyecto"}' http://localhost:8003/api/v1/projects
curl -s http://localhost:8003/api/v1/projects/PRJ/issues?label=bug | jq .
# → {"error":"feature_disabled","message":"label filtering is disabled (FEATURE_LABEL_FILTERING=false)"}  (400)

# Sobrescribir sin editar .env
export IMAGE_TAG="$(git rev-parse --short=8 HEAD)" APP_VERSION="$(git rev-parse --short=8 HEAD)"
FEATURE_LABEL_FILTERING=false docker compose --env-file deploy/dev.env -p hiss-dev up -d
```

La flag demuestra el patrón 12-factor: el mismo artefacto
(`ghcr.io/mvieitesr/hiss:<tag>`) se comporta distinto según el entorno que
lo ejecuta.

## Resumen de verificación

```sh
# Ningún secreto en ficheros versionados
grep -n '^POSTGRES_PASSWORD=' deploy/*.env && echo "ERROR" || echo "ok"

# Config por Environment visible y parametrizable
cat deploy/dev.env | grep -E "IMAGE|APP_PORT|FEATURE_LABEL_FILTERING"
cat deploy/prod.env | grep -E "IMAGE|APP_PORT|FEATURE_LABEL_FILTERING"
POSTGRES_PASSWORD=dummy IMAGE_TAG=deadbeef APP_VERSION=deadbeef IMAGE=example.invalid/x docker compose -f deploy/compose.yml --env-file deploy/dev.env -p hiss-docs-check config --images

# Compose valida presencia del secreto
POSTGRES_PASSWORD=dummy IMAGE_TAG=deadbeef APP_VERSION=deadbeef docker compose --env-file deploy/dev.env -p hiss-docs-check config -q && echo "config ok"
# Sin contraseña debe fallar
POSTGRES_PASSWORD= IMAGE_TAG=deadbeef APP_VERSION=deadbeef docker compose --env-file deploy/dev.env -p hiss-docs-check config -q && echo "debe fallar" || echo "falla como debe"

# Feature flag en código y tests
grep -n FEATURE_LABEL_FILTERING app/app/__init__.py
grep -n FEATURE_LABEL_FILTERING app/tests/test_probes_version_flag.py
grep -n FEATURE_LABEL_FILTERING deploy/*.env

# Despliegue con secreto inyectado
export POSTGRES_PASSWORD='elige-un-secreto-local'
export IMAGE_TAG="$(git rev-parse --short=8 HEAD)" APP_VERSION="$(git rev-parse --short=8 HEAD)" # SHA8 publicado
docker compose -f deploy/compose.yml --env-file deploy/dev.env -p hiss-dev up -d --wait --wait-timeout 60
curl --fail http://localhost:8001/healthz | jq .
curl --fail http://localhost:8001/readyz  | jq .
curl --fail http://localhost:8001/version | jq .
```

Ver también `docs/release-process.md` para cómo ese mismo mecanismo se usa
durante promociones y rollbacks, y `deploy/compose.yml` para la definición
canónica de servicios.
