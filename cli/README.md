# hiss CLI

Cliente con Typer + httpx + rich para la API de hiss.

## Instalación

```
pip install -e cli/
hiss --help
```

## Uso

```
hiss --url http://localhost:8000 projects list
hiss projects create --key OPS --name "Operations"
hiss issues list --project OPS --status open
hiss comments add 42 "reproduced on staging"
hiss labels create bug
```

La URL base se establece con la opción `--url` o la variable de entorno `HISS_URL` (por defecto `http://localhost:8000`).

La salida se muestra como tabla por defecto; los comandos compatibles aceptan `--json`. El texto se muestra literalmente, sin interpretar el marcado de Rich. El cliente codifica los segmentos dinámicos de la ruta URL; la API rechaza `/`, `.` y `..` como claves de Project o nombres de Label y aplica los límites de longitud descritos en el README de la raíz.

Una respuesta 2xx exitosa y no vacía debe ser JSON (se acepta 204 o un cuerpo vacío). De lo contrario, la CLI termina con el estado 1 y escribe `Error: non-JSON response from API; check the base URL.` en stderr.

Las dependencias de ejecución están fijadas en `pyproject.toml`: `typer==0.27.3`, `httpx==0.28.1` y `rich==15.0.0`; `requirements.txt` también fija pytest para los tests.
