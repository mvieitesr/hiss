# ADR 0001: Runner autoalojado y GitHub Environments como mecanismo de CD

- **Estado:** Aceptado
- **Fecha:** 2025-09-01
- **Decisores:** Equipo docente, mantenedores del repo

> **Actualización:** La decisión de usar runners y Environments sigue vigente. El pipeline actual deriva GHCR del dueño en minúsculas; dev exige SHA8 en `IMAGE_TAG` y `APP_VERSION`, y los CD promocionan y despliegan por digest (`IMAGE_TAG=tag@digest`). El comando de la decisión recoge el diseño histórico; ver `docs/pipeline.md` y `docs/setup.md` para el flujo vigente y la seguridad del runner.

## Contexto

El repo es material docente autoalojable: cada estudiante despliega
`dev` en `8001`, `staging` en `8002` y `prod` en `8003` en su propia
máquina con el mismo `deploy/compose.yml` y tres `deploy/*.env`. Los
runners hospedados por GitHub (`ubuntu-latest`) no pueden alcanzar
`localhost` del estudiante, por lo que un `docker compose pull`/`up -d`
hacia `hiss-dev`/`hiss-staging`/`hiss-prod` fallaría desde la nube.

Necesitábamos un mecanismo que permitiera construir la imagen en la nube
(`_build-push.yml` empuja a `ghcr.io/mvieitesr/hiss:<tag>` con
`GITHUB_TOKEN`) y desplegarla en el host del estudiante sin exponer su
máquina a internet ni requerir infra cloud por alumno.

Requisitos docentes:

- El estudiante debe poder seguir `docs/setup.md` en su portátil macOS o
  Linux sin cuenta cloud.
- El runner debe tener `Docker Compose v2` y `curl`/`jq` para los smoke
  tests (`curl --fail .../healthz|/readyz|/version | jq --arg expected`).
- `prod` debe distinguir Delivery de Deployment con un gate manual.

## Decisión

Usar **runner autoalojado** con etiqueta `self-hosted` más **GitHub
Environments** `dev`/`staging`/`prod` como mecanismo de CD:

- `cd-dev.yml`, `cd-staging.yml`, `cd-prod.yml` y `rollback.yml` declaran
  `runs-on: [self-hosted]` sin `linux` para que funcionen en macOS
  (ver `cd-dev.yml: runs-on: [self-hosted]` y `cd-dev.yml:jobs:deploy`).
- Cada `deploy` inyecta `POSTGRES_PASSWORD: ${{ secrets.POSTGRES_PASSWORD }}`
  desde el Environment correspondiente y ejecuta
  `POSTGRES_PASSWORD="$POSTGRES_PASSWORD" IMAGE_TAG="$DEPLOY_TAG" APP_VERSION="$DEPLOY_TAG" docker compose -f deploy/compose.yml --env-file deploy/<env>.env -p hiss-<env> pull && up -d`.
- `prod` declara `environment: prod` con `Required reviewers` (ver
  `docs/setup.md:GitHub Environments y secretos`), lo que pausa
  `cd-prod.yml` y `rollback.yml` hacia `prod` hasta aprobación.
- El paquete `ghcr.io/mvieitesr/hiss` se publica como **público** para que
  el runner haga `pull` anónimo sin `docker login`; los `push` usan
  `permissions: packages: write` en `_build-push.yml`.

## Alternativas consideradas y rechazadas

| Alternativa | Por qué se rechazó |
| --- | --- |
| **Watchtower polling** (contenedor que hace `pull` periódico del registro) | Polling oculta el trigger, añade latencia configurable, requiere otro contenedor siempre activo y no enseña Actions. No hay gate de `prod` ni smoke tests visibles en el workflow. |
| **SSH hacia localhost** (runner en la nube hace `ssh` al portátil via túnel/reverse proxy) | Exige abrir puerto o túnel (`ngrok`, `tailscale`), gestionar claves `SSH` y exponer `POSTGRES_PASSWORD` por canal. Frágil en redes de campus/NAT y contradice el objetivo de cero infra cloud. |
| **Hosting cloud** (desplegar `dev`/`staging`/`prod` en VM/cloud gratuita por alumno) | Cada alumno necesitaría cuenta cloud, costes, cuotas y teardown. El curso quiere que todo corra en local sin tarjeta de crédito ni limpieza de recursos cloud. Además ocultaría el aislamiento `COMPOSE_PROJECT_NAME`/`pgdata` en un mismo host. |

## Consecuencias

**Positivas:**

- Cero infra extra por alumno — solo Docker y un runner en su máquina.
- `ci.yml` sigue en `ubuntu-latest`; solo CD toca la máquina local, lo
  que separa claramente verificación y entrega.
- Gate de `prod` enseña Delivery vs Deployment sin código adicional.

**Negativas / obligaciones:**

- **Invariante de seguridad:** cada workflow de CD empieza con
  `# Safety invariant: this workflow deploys only owner-controlled pushes to main.`
  `# Never add pull_request: untrusted fork code must not execute on the self-hosted runner.`
  Nunca añadir `on: pull_request` a un job `self-hosted` — código de un
  fork podría robar `POSTGRES_PASSWORD` o comprometer el host.
- `cd-dev.yml: runs-on: [self-hosted]` sin `linux` — documentado para que macOS
  funcione; añadir `linux` rompería runners en Apple Silicon.
- Invariante `Never add pull_request` citado arriba aplica a todo `runs-on: [self-hosted]`.
- Requisitos del host: `Docker Engine + Compose v2`, `curl`, `jq` (ver
  `docs/setup.md:Requisitos del host`).
- `POSTGRES_PASSWORD` vive como secreto de Environment (`gh secret set POSTGRES_PASSWORD --env dev`), nunca en `deploy/*.env`.
- El paquete GHCR debe cambiarse a público manualmente tras el primer
  `push` a `main`; si permanece privado, `docker pull` en el runner falla
  con `unauthorized`.
- El runner debe mantenerse `Idle`; si está `Offline`, los workflows quedan
  encolados.

**Reversibilidad:** si el curso migra a cloud, bastaría cambiar `runs-on`
a `ubuntu-latest` y exponer los tres puertos, pero se perdería la lección
de autoalojado.

## Referencias

- `.github/workflows/cd-dev.yml`, `cd-staging.yml`, `cd-prod.yml`, `rollback.yml`
- `.github/workflows/_build-push.yml`
- `deploy/compose.yml`, `deploy/*.env`
- `docs/setup.md`, `docs/pipeline.md`, `docs/environments.md`
