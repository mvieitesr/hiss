# Configuración del repositorio

## Integración continua

El repositorio tiene un único workflow de CI,
`.github/workflows/ci.yml` (además de los workflows de CD y rollback). Se ejecuta en las pull requests y en los pushes a
`main`. Todos los jobs usan runners hospedados por GitHub (`ubuntu-latest`).
Una ejecución completa normal debería terminar en menos de tres minutos; si
tarda más, trátalo como una regresión — un pipeline lento es un mal artefacto
docente.

El workflow detecta primero las áreas modificadas y después ejecuta sólo las
comprobaciones relevantes:

- `lint-pipeline` siempre ejecuta actionlint 1.7.12 y valida ambos Compose para los tres env-files con valores ficticios.
- El lint de Python usa Ruff 0.9.10 (`ruff check app cli` y
  `ruff format --check app cli`).
- `lint-docker` ejecuta Hadolint contra `app/Dockerfile`.
- `test-app` aplica las migraciones de Alembic y ejecuta los tests de Flask
  contra un contenedor de servicio efímero `postgres:17-alpine`.
- `test-cli` ejecuta los tests del CLI sin contenedor de servicio.
- `build` ejecuta `docker build -f app/Dockerfile app/` después de los tests de
  la aplicación. Sólo valida la imagen: no hace login en ningún registro, no
  publica ninguna imagen ni despliega nada.

El job `changes` usa filtros de rutas. Un cambio en la aplicación ejecuta sus
comprobaciones y la construcción de la imagen; un cambio sólo en el CLI ejecuta
el lint de Python y los tests del CLI, pero se salta los tests de la
aplicación, el lint del Dockerfile y la construcción de la imagen. Los cambios
en archivos compartidos como `pytest.ini`, `ruff.toml`, `.github/workflows/**`, `deploy/**` o `compose.yml`
ejecutan ambas suites de tests. Un cambio que sólo toca documentación puede
dejar jobs de paquetes saltados; GitHub informa de los jobs requeridos
saltados como exitosos, así que esto no elude una comprobación fallida en un
cambio relevante.

## Proteger `main`

La protección de rama es deliberadamente un ajuste manual del repositorio en
GitHub, no un paso más de automatización. Después de que la primera ejecución
del workflow haga disponibles las comprobaciones:

1. Abre **Settings → Branches** (o **Rules → Rulesets**) en el repositorio.
2. Añade una regla para `main` y exige pull requests antes de fusionar.
3. Exige que las comprobaciones de estado pasen antes de fusionar. Selecciona
   las que aparecen como `CI / Detect changes`, `CI / Validate workflows and Compose`, `CI / Lint Python`,
   `CI / Lint Dockerfile`, `CI / Test app`, `CI / Test CLI` y
   `CI / Build app image`.
4. Guarda la regla. Mantenla activada también para administradores si el
   repositorio se usa como la puerta de fusión de la lección de CI/CD.

Una comprobación requerida en rojo bloquea el merge; una en verde (o saltada
por el filtro de rutas) es el permiso para continuar. Los runners
autoalojados quedan reservados para el trabajo de despliegue.

## Revisar una ejecución

El worker no hace push desde el checkout local. Después de que el orquestador
haga push de la rama, localiza y observa la ejecución real con comandos
acotados:

```sh
gh run list --workflow ci.yml --limit 5
gh run watch <run-id> --exit-status
gh run view <run-id> --log-failed
```

También puedes usar `gh workflow view ci.yml` una vez que el workflow existe en GitHub. CI no tiene puerta de cobertura ni job de mypy, y no publica ni despliega imágenes.

## Entrega continua

Tres workflows de CD despliegan cada artefacto aceptado en tu propia máquina,
y un cuarto permite hacer rollback. Todos los despliegues se ejecutan en un
runner `[self-hosted]` que debe tener Docker Compose y `curl`/`jq`
disponibles; `linux` no forma parte de la etiqueta del runner, así que los
runners en macOS también funcionan.

| Disparador | Workflow | Tag de imagen | Environment | Puerta |
| --- | --- | --- | --- | --- |
| CI en verde tras `push` a `main` | `cd-dev.yml` | SHA de 8 caracteres | `dev` (`:8001`) | CI debe ser `success` |
| `push` de tag `X.Y.Z-snapshot` | `cd-staging.yml` | `X.Y.Z-snapshot` | `staging` (`:8002`) | `ci-gate` + automático |
| `push` de tag `X.Y.Z` | `cd-prod.yml` | `X.Y.Z` | `prod` (`:8003`) | `ci-gate` + aprobación del Environment |

Los tags no deben llevar una `v` inicial y `pull_request` nunca despliega —
cada workflow de despliegue comenta este invariante de seguridad en su
cabecera. `cd-dev` construye con `app/Dockerfile`; staging y prod promocionan el digest de la imagen SHA8 ya publicada por el reusable. Este deriva `ghcr.io/<dueño-en-minúsculas>/hiss`, usa `GITHUB_TOKEN` y `packages: write`, y verifica la etiqueta OCI de revisión. Los jobs de deploy hacen `pull` de `IMAGE_TAG=<tag>@<digest>` y `up -d --no-build --pull never` con `APP_VERSION=<tag>` y el secreto del Environment. El smoke comprueba `/healthz`, `/readyz` y `/version`; este último refleja configuración, no certifica por sí solo la imagen.

### Mutabilidad de los tags

- `X.Y.Z-snapshot` es un **tag móvil** — puedes borrarlo y volver a subirlo
  mientras endureces una release. La contrapartida es que el historial de
  staging no es estrictamente inmutable.
- `X.Y.Z` es **inmutable por convención** una vez subido; nunca lo muevas ni lo vuelvas a subir. GitHub no lo impone sin reglas externas; una regla `v*` no protege estos nombres.

### Prerrequisitos

1. **Runner autoalojado** registrado con la etiqueta `self-hosted` en la
   máquina que ejecutará los tres Environments (requiere Docker Engine y plugin Compose).
2. **GitHub Environments** `dev`, `staging` y `prod` creados en el
   repositorio; cada uno guarda un secreto `POSTGRES_PASSWORD` (nunca
   versionado). `prod` tiene un revisor requerido (tú) para que el job de
   despliegue pause a la espera de aprobación — la distinción entre
   Continuous Delivery y Continuous Deployment.
3. **Paquete GHCR del dueño del repositorio** accesible al runner; hacerlo público permite `pull` anónimo. El build usa `GITHUB_TOKEN` con `packages: write`. En un fork hay que habilitar Actions y vincular/autorizar el paquete propio al repositorio, especialmente si ya se publicó manualmente.

Los tres puntos anteriores se detallan a continuación: prepara Environments, secretos y paquete aunque ya tengas runner. La primera publicación puede crear un paquete privado; hazlo accesible antes del primer pull del runner y reintenta el CD si es necesario.

## Runner autoalojado — registro, instalación y operación

Todos los despliegues de CD se ejecutan en un runner con etiqueta
`self-hosted`. El runner debe vivir en la máquina donde quieres que corran
`hiss-dev` en `8001`, `hiss-staging` en `8002` y `hiss-prod` en `8003`.
En un fork registra un runner propio y usa `tu-usuario/hiss` en los comandos; verifica también que `gh` apunta al repositorio correcto. Mantén deploy y smoke en el mismo host si registras más de un runner.

### Requisitos del host

- **Docker Engine + plugin Compose** compatible con `docker compose` y accesible al usuario del runner.
- **`curl` y `jq`** — necesarios para los smoke tests de los workflows
  (`curl --fail .../healthz` y `jq --arg expected`). En macOS:
  `brew install curl jq`; en Debian/Ubuntu:
  `sudo apt-get update && sudo apt-get install -y curl jq`.
- Sistema operativo soportado: **macOS (Intel o Apple Silicon)** y
  **Linux x64** (Ubuntu 22.04/24.04, Debian 12, Fedora). `linux` no forma parte
  de la etiqueta del runner, así que macOS funciona igual con
  `runs-on: [self-hosted]`.

### 1. Registrar el runner en GitHub

**Opción A — interfaz web (recomendada la primera vez):**

1. Abre tu fork en GitHub: `https://github.com/tu-usuario/hiss`.
2. Ve a **Settings → Actions → Runners → New self-hosted runner**.
3. Selecciona **Linux** o **macOS** y arquitectura (`x64` / `ARM64`).
   GitHub muestra los comandos exactos de descarga y el token de registro.
4. El token expira en una hora; si caduca, genera uno nuevo con
   **New self-hosted runner** o vía API.

**Opción B — token vía `gh` CLI (útil para automatizar o renovar):**

```sh
# Autentícate una vez contra tu fork
gh auth login

# Obtén un token de registro efímero (válido ~60 min)
gh api --method POST /repos/tu-usuario/hiss/actions/runners/registration-token --jq .token
```

Guarda el valor impreso como `REG_TOKEN`; lo usarás en `./config.sh`.

### 2. Descargar, configurar y ejecutar

Usa **Settings → Actions → Runners → New self-hosted runner** para obtener los comandos actuales de descarga y registro para tu sistema y arquitectura. Sigue la secuencia mostrada por GitHub en el directorio dedicado `~/actions-runner`; usa el token efímero `REG_TOKEN` en el paso de configuración. No reutilices paquetes antiguos: `checkout@v7` requiere runner 2.327.1 o posterior. Comprueba en primer plano con `./run.sh` antes de instalar el servicio.

Para ejecutarlo como servicio en segundo plano, en **Linux** usa `sudo ./svc.sh install`, `sudo ./svc.sh start` y `sudo ./svc.sh status` (systemd). En **macOS** usa los mismos comandos sin `sudo`: `./svc.sh install`, `./svc.sh start` y `./svc.sh status` (launchd). Alternativamente deja `./run.sh` en una terminal dedicada. El runner aparece en **Settings → Actions → Runners** como `Idle`.

Verifica que Docker es accesible desde el runner:

```sh
docker compose version
docker run --rm hello-world
curl --version | head -1
jq --version
```

> **Advertencia de seguridad — invariante del repositorio**
>
> Los workflows de despliegue `cd-dev.yml`, `cd-staging.yml`, `cd-prod.yml` y
> `rollback.yml` declaran en su cabecera:
>
> ```yaml
> # Safety invariant: this workflow deploys only owner-controlled pushes to main.
> # Never add pull_request: untrusted fork code must not execute on the self-hosted runner.
> ```
>
> **Nunca añadas `pull_request` como disparador de un job `runs-on: [self-hosted]`**.
> Un runner autoalojado ejecuta código con acceso a tu máquina y a tus secretos
> `POSTGRES_PASSWORD`; si aceptara PRs de forks, cualquier persona podría
> robar secretos o comprometer el host. Esta es la razón por la que `ci.yml`
> usa `ubuntu-latest` y los despliegues usan `self-hosted`. Un PR también puede modificar workflows: usa una VM dedicada sin datos ni credenciales personales, exige aprobación de todos los colaboradores externos y revisa los cambios de workflows antes de aprobar. Mantén el runner parado fuera de la práctica; esto no elimina todo el riesgo.

### 3. Detener, reiniciar y desinstalar

```sh
# Linux: detener el servicio (en macOS, usa ./svc.sh sin sudo)
sudo ./svc.sh stop
# Reiniciar
sudo ./svc.sh start
# Ver logs del servicio (Linux)
journalctl -u actions.runner.*.service -f
# Ver logs del servicio (macOS)
launchctl list | grep actions.runner

# Desinstalar completamente el runner de la máquina
sudo ./svc.sh uninstall
# Elimina el registro en GitHub (necesita un token de eliminación)
REG_REMOVE_TOKEN=$(gh api --method POST /repos/tu-usuario/hiss/actions/runners/remove-token --jq .token)
./config.sh remove --token $REG_REMOVE_TOKEN
# o borra el directorio
cd ~ && rm -rf ~/actions-runner
```

Si solo quieres pausar los despliegues sin desinstalar, detén el servicio con
`sudo ./svc.sh stop` en Linux, `./svc.sh stop` en macOS, o termina `./run.sh` con `Ctrl+C`; GitHub mostrará el
runner como `Offline` y los workflows quedarán encolados hasta que vuelva.

## GitHub Environments y secretos

Los tres despliegues usan el mismo `deploy/compose.yml` con distinto
`--env-file`. El secreto `POSTGRES_PASSWORD` nunca se versiona; cada
Environment lo inyecta en el runner.

### Crear los tres Environments

**Interfaz web:**

1. Ve a **Settings → Environments → New environment**.
2. Crea `dev`, luego `staging`, luego `prod` (nombres en minúsculas,
   exactamente así: los workflows referencian `environment: dev|staging|prod`).
3. En cada Environment, pulsa **Add environment secret** y añade
   `POSTGRES_PASSWORD` con el mismo valor que usarás en local (por ejemplo
   `elige-un-secreto-local`; en producción usa un secreto largo distinto
   por Environment si lo prefieres, pero documenta cuál usas).
4. Solo en `prod`: activa **Required reviewers** y añádete como revisor.
   Esto hace que `cd-prod.yml` y `rollback.yml` hacia `prod` pausen hasta
   tu aprobación — la diferencia entre Delivery y Deployment.

**CLI con `gh`:**

```sh
# Crea los Environments (idempotente)
gh api --method PUT /repos/tu-usuario/hiss/environments/dev
gh api --method PUT /repos/tu-usuario/hiss/environments/staging
gh api --method PUT /repos/tu-usuario/hiss/environments/prod

# Añade el secreto a cada Environment (te pedirá el valor de forma interactiva)
gh secret set POSTGRES_PASSWORD --env dev
gh secret set POSTGRES_PASSWORD --env staging
gh secret set POSTGRES_PASSWORD --env prod
# Para lectura desde stdin, omite --body (evita imprimir el secreto).
# gh secret set POSTGRES_PASSWORD --env dev < fichero-secreto
```

La CLI anterior crea el Environment pero no configura su revisor: activa **Required reviewers** en `prod` en la interfaz web antes de continuar. Confirma que `gh` apunta a tu fork.

Verifica:

```sh
gh api /repos/tu-usuario/hiss/environments --jq '.environments[].name'
# Debe listar: dev, staging, prod
gh secret list --env dev | grep POSTGRES_PASSWORD
gh secret list --env staging | grep POSTGRES_PASSWORD
gh secret list --env prod | grep POSTGRES_PASSWORD
```

### Probar que el secreto llega al runner

Después de preparar el paquete GHCR como se describe abajo, haz un `push` a `main` y espera a que `ci.yml` termine en verde. Entonces
arranca `cd-dev.yml`; el job `Deploy dev` debe mostrar `environment: dev` y
no fallar por `POSTGRES_PASSWORD must be set`. Si CI falla, CD no llega a
desplegar. Si CD falla por el secreto, revisa que existe en `dev` y que el
runner está `Idle`.

## Paquete GHCR en público

Los workflows publican en `ghcr.io/<dueño-en-minúsculas>/hiss` vía `_build-push.yml`. Habilita Actions en tu fork y conecta el paquete al repositorio, concediendo acceso a Actions si fue publicado manualmente antes. El runner necesita acceso de pull; aquí se usa un paquete público.

**Hacer público el paquete (solo su propietario):**

1. Abre tu repositorio y entra en **Packages → hiss** una vez publicada la primera imagen.
2. En **Package settings → Visibility** pulsa **Change visibility → Public** y confirma.
3. Comprueba con configuración Docker aislada y un SHA8 realmente publicado (no borres tus credenciales habituales):

```sh
OWNER=tu-usuario  # en minúsculas
SHA8=$(git rev-parse --short=8 HEAD)  # commit cuya imagen ya publicó cd-dev
DOCKER_CONFIG=$(mktemp -d)
docker --config "$DOCKER_CONFIG" pull "ghcr.io/$OWNER/hiss:$SHA8"
rm -rf "$DOCKER_CONFIG"
```

Si aún no hay paquete, publica primero mediante un CI exitoso de `push` a `main`; el primer deploy puede fallar hasta hacer público el paquete. Las imágenes de ejemplo `0.1.0`, `0.1.1` y `0.1.0-snapshot` de `mvieitesr/hiss` las publicará el responsable del repositorio antes de la práctica.

Si el paquete sigue privado, los jobs de despliegue fallarán con
`unauthorized` en `docker pull`. Los `push` no se ven afectados porque usan
`GITHUB_TOKEN` con `packages: write` dentro del workflow.

> La visibilidad pública no expone `POSTGRES_PASSWORD`; solo expone las
> capas de la imagen, que no contienen secretos.

### Rollback

`rollback.yml` sólo se dispara con `workflow_dispatch` (no construye nada) —
redespliega cualquier tag anterior en cualquier Environment. Los rollbacks a
prod siguen requiriendo la aprobación del Environment `prod`.

- **Interfaz web:** Actions → Rollback → Run workflow → elige `environment`
  (`dev` | `staging` | `prod`) y `tag`.
- **CLI:**

```sh
gh workflow run rollback.yml -f environment=prod -f tag=0.1.0
# o para staging:
gh workflow run rollback.yml -f environment=staging -f tag=0.1.0-snapshot
gh run list --workflow rollback.yml --limit 5
gh run view <run-id> --log-failed
```

> La ceremonia completa de release, la checklist de promoción y el
> runbook de rollback viven en `docs/release-process.md`. La sección
> anterior es el resumen operativo; el runbook es la referencia canónica.

