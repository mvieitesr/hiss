# hiss CLI

Typer + httpx + rich client for the hiss API.

## Install

```
pip install -e cli/
hiss --help
```

## Usage

```
hiss --url http://localhost:8000 projects list
hiss projects create --key OPS --name "Operations"
hiss issues list --project OPS --status open
hiss comments add 42 "reproduced on staging"
hiss labels create bug
```

Base URL from `--url` flag or `HISS_URL` env (default `http://localhost:8000`).

Table output by default; supported commands accept `--json`. Text is rendered literally, without interpreting Rich markup. Dynamic URL path segments are encoded by the client; the API rejects `/`, `.` and `..` as Project keys or Label names and enforces the length limits described in the root README.

A successful non-empty 2xx response must be JSON (204 or an empty body is accepted). Otherwise the CLI exits with status 1 and prints `Error: non-JSON response from API; check the base URL.` to stderr.

Runtime dependencies are pinned in `pyproject.toml`: `typer==0.27.3`, `httpx==0.28.1` and `rich==15.0.0`; `requirements.txt` also pins pytest for tests.
