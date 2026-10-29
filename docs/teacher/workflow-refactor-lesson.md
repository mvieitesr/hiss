# Lección — Refactor de workflows duplicados a workflow reutilizable

> **Orientado al profesor — teacher-only.** Plan de clase para el profesor. Los estudiantes pueden
> leerlo después, pero la actividad está diseñada para ser guiada en aula.
> Requiere haber visto `docs/pipeline.md` y `docs/setup.md`.

Esta lección convierte un defecto intencional en aprendizaje. El tag
`workflows-duplicated` contiene los tres workflows de CD con `build` y
`push` duplicados inline; `main` los extrae a un workflow reutilizable
`_build-push.yml`. El alumno comprueba el tag, inspecciona el diff y
discute por qué `workflow_call` es la abstracción correcta.

## Objetivo

Que el alumno distinga duplicación accidental de abstracción útil y entienda
`workflow_call` con `inputs`, `outputs` y `permissions`, distinguiendo el histórico del pipeline actual.

## Prerrequisitos

- Repo clonado con acceso a `origin` y tag `workflows-duplicated`: `git fetch --tags`. El tag puede no estar en el fork del curso; el responsable debe prepararlo antes de clase o facilitar su procedencia.
- Haber leído `docs/pipeline.md` § `_build-push.yml` y § `cd-dev.yml`.
- Conocer `docker/build-push-action@v6` y `docker/login-action@v3` a nivel
  de lectura — no es necesario ejecutarlos en clase.

## Material

- Tag `workflows-duplicated` (commit `963d38e`): `cd: duplicated first-pass
  delivery workflows and manual rollback`.
- `main` actual con `_build-push.yml`.

## Guion (45–60 min)

### 0. Contexto (5 min)

El repo entregó CD por primera vez con tres ficheros idénticos salvo el
trigger y el Environment. Funcionaba, pero cada cambio de `login` o
`build-push` había que repetirlo tres veces. La deuda técnica se etiquetó
adrede para enseñar el refactor.

Pregunta de apertura: ¿dónde está la duplicación y por qué duele?

### 1. Inspeccionar el tag (10 min)

```sh
git fetch --tags
git tag --list | grep workflows-duplicated
git show workflows-duplicated --stat
```

Debe mostrar:

```
.github/workflows/cd-dev.yml     |  99 +++++++++++++++++++
.github/workflows/cd-prod.yml    | 101 ++++++++++++++++++++
.github/workflows/cd-staging.yml | 101 ++++++++++++++++++++
.github/workflows/rollback.yml   |  99 +++++++++++++++++++++
```

Sin `_build-push.yml`.

Ver un workflow duplicado:

```sh
git show workflows-duplicated:.github/workflows/cd-dev.yml
```

Snippet relevante (antes del refactor), con la ruta histórica del registro anonimizada; consulta el tag para ver el literal:

```yaml
  build:
    name: Build and push dev image
    needs: prepare
    runs-on: ubuntu-latest
    timeout-minutes: 10
    steps:
      - name: Check out repository
        uses: actions/checkout@v4
      - name: Log in to GHCR
        uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}
      - name: Build and push image
        uses: docker/build-push-action@v6
        with:
          context: ./app
          file: ./app/Dockerfile
          push: true
          tags: <registro-histórico>/hiss:${{ needs.prepare.outputs.tag }}
```

Hacer lo mismo con `cd-staging.yml` y `cd-prod.yml` — son idénticos salvo
el nombre del job y el tag de entrada.

```sh
git show workflows-duplicated:.github/workflows/cd-staging.yml | grep -A5 "Build and push"
git show workflows-duplicated:.github/workflows/cd-prod.yml | grep -A5 "Build and push"
```

Alternativa sin `git show` (útil si el alumno prefiere checkout):

```sh
git checkout workflows-duplicated -- .github/workflows/cd-dev.yml
cat .github/workflows/cd-dev.yml | sed -n '/Build and push/,/tags:/p'
git checkout main -- .github/workflows/cd-dev.yml  # restaurar
```

### 2. Diff al `main` actual (15 min)

```sh
git diff workflows-duplicated..main -- .github/workflows/_build-push.yml
git diff workflows-duplicated..main -- .github/workflows/cd-dev.yml
git diff workflows-duplicated..main -- .github/workflows/cd-staging.yml
git diff workflows-duplicated..main -- .github/workflows/cd-prod.yml
```

**Refactor histórico vs pipeline actual:**

El commit `fdab845` extrajo el build duplicado y usaba `secrets: inherit`. Compáralo con `workflows-duplicated` si quieres aislar ese paso. En `main` el reusable ha evolucionado: recibe `tag`, `ref` y `source_tag`, expone `image` y `digest`, deriva GHCR del dueño en minúsculas y verifica la revisión OCI antes de promocionar el digest. `cd-dev` construye; staging y prod promocionan el SHA8 sin reconstruir. Los callers actuales no usan `secrets: inherit`.

```sh
git diff workflows-duplicated..fdab845 -- .github/workflows/_build-push.yml .github/workflows/cd-dev.yml
git show main:.github/workflows/_build-push.yml
git show main:.github/workflows/cd-staging.yml
```

El diff a `main` también contiene cambios posteriores (CI gate, acciones actualizadas, seguridad y promoción); no todos son parte del refactor original.

### 3. Discusión guiada (15 min)

1. **¿Por qué `workflow_call` y no una action compuesta?** El primero permite reutilizar un workflow completo con jobs; una action compuesta agrupa steps.
2. **¿Qué deciden los callers?** El tag, el commit y si se construye o promociona. La revisión OCI y el digest protegen la identidad del artefacto durante la promoción.
3. **¿Qué ocurrió con `secrets: inherit`?** Se usó en el refactor histórico, no en los callers actuales. `GITHUB_TOKEN` está disponible para el reusable con los permisos permitidos por el caller; heredar todos los secretos no es necesario para ese token.
4. **¿Por qué `contents: read, packages: write`?** El reusable necesita esos permisos y el caller no puede concederle permisos superiores a los suyos.
5. **¿Cuándo no abstraer?** Cuando los builds son sustancialmente distintos. Actualmente el reusable tiene dos caminos explícitos: construir o promocionar.
6. **¿Qué queda duplicado a propósito?** Los triggers, preparación y despliegues/smoke tests por Environment.

### 4. Cierre y tarea (5 min)

- Tarea: proponer un siguiente refactor — por ejemplo extraer `deploy` a
  workflow reutilizable con `inputs: environment, tag, port`. Debatir si
  merece la pena o si la duplicación de `deploy` es accidental pero estable.
- Referencia: `docs/pipeline.md:### _build-push.yml` y `fdab845 cd: extract
  reusable build-push workflow from CD callers` (mensaje de commit).

## Comandos de referencia para el alumno

```sh
git fetch --tags
git show workflows-duplicated:.github/workflows/cd-dev.yml | less
git diff workflows-duplicated..main -- .github/workflows/_build-push.yml
git diff workflows-duplicated..main -- .github/workflows/cd-dev.yml
git log --oneline workflows-duplicated..main | cat
# restaurar si se hizo checkout del tag:
git checkout main -- .github/workflows/
```

## Notas para el profesor

- No ejecutar workflows en clase — la inspección es estática. Si quieres
  demo en vivo, empuja un commit vacío a `main` y observa primero `ci.yml`
  y, solo si termina en verde, `cd-dev.yml` en **Actions**.
- El tag `workflows-duplicated` se creó adrede para esta lección; no lo borres. Si falta, consulta al responsable antes de recrearlo desde `963d38e`.
- Tiempo: si la clase es de 90 min, añade ejercicio práctico: el alumno
  crea una rama, revierte el refactor (copia el `build` inline) y abre PR
  para ver `ci.yml` verde pero diff mayor.
