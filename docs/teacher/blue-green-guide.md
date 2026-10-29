# Guía docente — demo blue-green en clase

> **Orientado al profesor — teacher-only.** Cómo ejecutar la demo `deploy/blue-green/` en aula sin
> improvisar. Para la teoría completa ver `deploy/blue-green/README.es.md`
> (arquitectura, `switch.sh`, `nginx.conf.template`) y
> `docs/deployment-strategies.md:## Blue-Green`.

Esta guía es el runbook del profesor: tiempos, comandos copy-paste,
checklist y limpieza. No duplica el README — lo referencia y añade lo que
un docente necesita para no perder la clase en esperas.

## Objetivo de la demo

Que el alumno vea un corte blue-green sin downtime con sus propios ojos:
dos `curl` a `/version` antes y después de `switch.sh` y un bucle continuo
que no falla durante el `nginx -s reload`.

## Prerrequisitos del aula

- Docker Engine + Compose v2 en el ordenador del profesor y, si es posible,
  en los portátiles de los alumnos.
- `curl` y `jq` instalados.
- `POSTGRES_PASSWORD` disponible (usa `changeme` para la demo; no es secreto
  docente).
- Imágenes `0.1.0`, `0.1.1` y `0.1.0-snapshot` publicadas en el GHCR elegido.
  Por defecto se usa `ghcr.io/vieitesss/hiss` público; cada fork puede usar
  su propio repositorio exportando `IMAGE=ghcr.io/<usuario>/hiss`.
- Puerto `9000` libre. Si está ocupado, exporta `BLUE_GREEN_PORT=9001`
  para toda la sesión y sustituye `9000` por `9001` en los comandos `curl`.
- Repo en `main` limpio (`git status` sin cambios).

## Preparación (5 min antes de clase)

```sh
git fetch --tags
git checkout main
git pull --ff-only origin main

# usa el mismo secreto durante toda la sesión, también para los scripts
export POSTGRES_PASSWORD=changeme
# Opcional: export IMAGE=ghcr.io/<usuario>/hiss
# limpia restos de demos anteriores, incluidos datos y estado del proxy
docker compose -f deploy/blue-green/compose.yml down -v 2>/dev/null || true
docker ps -a | grep hiss-blue-green || echo "limpio"
```

Si quieres precalentar imágenes para no esperar pulls en clase:

```sh
docker pull "${IMAGE:-ghcr.io/vieitesss/hiss}:0.1.0"
docker pull "${IMAGE:-ghcr.io/vieitesss/hiss}:0.1.1"
docker pull "${IMAGE:-ghcr.io/vieitesss/hiss}:0.1.0-snapshot"
```

## Guion (20–30 min)

### 1. Levantar la demo (3 min, espera ≤60s)

```sh
docker compose -f deploy/blue-green/compose.yml --env-file deploy/blue-green/.env.example up -d --wait --wait-timeout 60

curl --fail --retry 10 --retry-delay 2 --retry-connrefused http://localhost:9000/healthz | jq .
curl --fail --retry 10 --retry-delay 2 --retry-connrefused http://localhost:9000/version | jq .
./deploy/blue-green/switch.sh status
```

El servicio `migrate` termina antes de arrancar ambos slots, evitando migraciones
simultáneas. Si el arranque falla o algún servicio no llega a `healthy` en 60s,
muestra `docker compose -f deploy/blue-green/compose.yml logs migrate` /
`blue` / `green` / `proxy` y aborta.

### 2. Mostrar el estado inicial (2 min)

```sh
curl -s http://localhost:9000/version | jq .
./deploy/blue-green/switch.sh status
docker compose -f deploy/blue-green/compose.yml ps
```

Pide a un alumno que lea la versión en voz alta. Apunta `blue: 0.1.0`.
Tras el switch, `green` debe responder `0.1.1`.

### 3. Zero-downtime — bucle + switch (5 min)

**Terminal A** — deja corriendo:

```sh
while true; do curl -fs http://localhost:9000/version >/dev/null || echo "fail $(date)"; sleep 0.1; done
```

**Terminal B** — corta:

```sh
./deploy/blue-green/switch.sh switch green
curl -s http://localhost:9000/version | jq .
./deploy/blue-green/switch.sh status
```

No debe aparecer `fail` en la terminal A. Explica: `nginx -s reload` lanza
workers nuevos con la nueva `proxy_pass` y drena los viejos — las
peticiones in-flight terminan, las nuevas van al otro color. En
producción K8s hace lo mismo con `terminationGracePeriodSeconds`.

Si aparece `fail`, es `proxy` no saludable o `BLUE_GREEN_PORT` distinto —
verifica `docker compose ps` y `curl -v http://localhost:9000/healthz`.

### 4. `deploy` en el slot inactivo (5 min)

```sh
./deploy/blue-green/switch.sh deploy 0.1.0-snapshot
# el script detecta el slot inactivo, hace BLUE_TAG=<tag> up -d <inactive>,
# primero migra con la imagen 0.1.0-snapshot; espera healthy ≤60s,
# hace switch y exige que /version coincida con el tag

curl -s http://localhost:9000/version | jq .
./deploy/blue-green/switch.sh status
```

Tiempo total de `deploy` ≤60s por el `wait_healthy` del script. Si tarda
más, `Ctrl+C` y muestra `docker logs`.

### 5. Rollback — mover el proxy de vuelta (2 min)

```sh
./deploy/blue-green/switch.sh rollback
curl -s http://localhost:9000/version | jq .
./deploy/blue-green/switch.sh status
# rollback blue-green = switch al color anterior, no redespliegue
```

Contrasta con `rollback.yml`: allí se redespliega `IMAGE_TAG`; aquí se
mueve el proxy y se verifica la versión del slot anterior. Las migraciones
no se revierten; deben ser compatibles con ambos colores.

### 6. Variante con script de verificación (opcional, 2 min)

Si prefieres un solo comando que deje evidencia:

```sh
POSTGRES_PASSWORD=changeme ./deploy/blue-green/demo-check.sh
# o con puerto alternativo:
BLUE_GREEN_PORT=9001 POSTGRES_PASSWORD=changeme ./deploy/blue-green/demo-check.sh
```

`demo-check.sh` comprueba la demo ya levantada, exige salud del proxy y
restaura el color inicial sin recrear los slots. No está cableado en CI a
propósito — es manual y su salida es el test.

## Checklist del profesor

- [ ] `git fetch --tags` y `git tag --list | grep workflows-duplicated` (para lección anterior)
- [ ] `docker compose -f deploy/blue-green/compose.yml config -q` sin errores
- [ ] `POSTGRES_PASSWORD` exportada para todos los comandos (sin versionarla)
- [ ] Puerto `9000` libre (`lsof -i :9000` o `ss -lptn 'sport = :9000'` vacío)
- [ ] `BLUE_TAG` y `GREEN_TAG` apuntan a tags publicados existentes
- [ ] `switch.sh` ejecutable (`chmod +x deploy/blue-green/switch.sh`)

## Limpieza (1 min, obligatorio)

```sh
docker compose -f deploy/blue-green/compose.yml down -v
docker ps -a | grep hiss-blue-green || echo "limpio"
docker volume ls | grep hiss-blue-green || echo "volumen limpio"
```

No dejes `hiss-blue-green` levantado junto a `hiss-dev`/`hiss-staging`/
`hiss-prod` — el alumno debe ver `docker ps` limpio al final.

## Errores comunes en clase

| Síntoma | Causa | Solución |
| --- | --- | --- |
| `pull access denied` | imagen no publicada o GHCR privado | `docker pull ghcr.io/vieitesss/hiss:0.1.0` debe funcionar sin `login`; haz el paquete público |
| `healthy` nunca llega | `POSTGRES_PASSWORD` no inyectada | revisa `POSTGRES_PASSWORD=changeme` delante del `compose up` |
| `curl: 502 Bad Gateway` tras `switch` | `ACTIVE_SLOT` renderizado con var vacía | verifica `deploy/blue-green/nginx.conf.template` usa `envsubst '${ACTIVE_SLOT}'` |
| `switch green` idempotente sin cambio | el proxy ya apunta a `green` | `./deploy/blue-green/switch.sh status` |
| `demo-check.sh: timeout` | `BLUE_GREEN_PORT` distinto al usado en `up` | pasa `BLUE_GREEN_PORT=9001` a ambos comandos |

## Referencias

- `deploy/blue-green/README.es.md` — arquitectura, `nginx.conf.template`,
  `switch.sh`, diagrama `sequenceDiagram` y tabla Recreate/Rolling/Canary.
- `docs/deployment-strategies.md` — visión de conjunto RA3 con Mermaid y
  discusión `0002_create_labels_issue_labels.py` (migración aditiva).
- `deploy/blue-green/compose.yml` y `.env.example` — valores por defecto
  `BLUE_TAG=0.1.0`, `GREEN_TAG=0.1.1`, `BLUE_GREEN_PORT=9000`.
- `deploy/blue-green/demo-check.sh` — verificación manual con
  `wait_healthy` acotado (60s) y `curl --retry`.
