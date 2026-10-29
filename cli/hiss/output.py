"""Output helpers — rich tables (default) and JSON (--json)."""

import json
import sys

import typer
from rich.console import Console
from rich.table import Table
from rich.text import Text


def print_json(data) -> None:
    typer.echo(json.dumps(data, indent=2))


def print_table(headers: list[str], rows: list[list[str]], title: str | None = None) -> None:
    table = Table(title=Text(title) if title is not None else None)
    for h in headers:
        table.add_column(h, overflow="fold")
    for row in rows:
        table.add_row(*[Text(str(c)) for c in row])
    # Create Console at call time so CliRunner's sys.stdout patch is respected.
    # Rich defaults to stderr; we force stdout for test capture while still
    # rendering correctly in a terminal.
    console = Console(file=sys.stdout, force_terminal=False, width=120)
    console.print(table)
