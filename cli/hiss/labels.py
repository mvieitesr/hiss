"""Labels command group — thin HTTP mapping."""

import httpx
import typer

import hiss.client
from hiss.output import print_json, print_table

labels_app = typer.Typer(help="Manage Labels")


@labels_app.command("list")
def list_labels(
    ctx: typer.Context,
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """List Labels."""
    base_url = hiss.client.get_base_url_for_ctx(ctx)
    try:
        with hiss.client.get_client(ctx) as client:
            resp = client.get("/api/v1/labels")
    except httpx.RequestError as exc:
        hiss.client.handle_request_error(exc, base_url)
    data = hiss.client.handle_response(resp)
    if json_output:
        print_json(data)
    else:
        if not data:
            typer.echo("No Labels found.")
        else:
            headers = ["id", "name"]
            rows = [[lb.get("id", ""), lb.get("name", "")] for lb in data]
            print_table(headers, rows, title="Labels")


@labels_app.command("create")
def create_label(
    ctx: typer.Context,
    name: str = typer.Argument(..., help="Label name"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Create a Label."""
    base_url = hiss.client.get_base_url_for_ctx(ctx)
    payload = {"name": name}
    try:
        with hiss.client.get_client(ctx) as client:
            resp = client.post("/api/v1/labels", json=payload)
    except httpx.RequestError as exc:
        hiss.client.handle_request_error(exc, base_url)
    data = hiss.client.handle_response(resp)
    if json_output:
        print_json(data)
    else:
        headers = ["id", "name"]
        rows = [[data.get("id", ""), data.get("name", "")]]
        print_table(headers, rows, title="Created Label")


@labels_app.command("delete")
def delete_label(
    ctx: typer.Context,
    name: str = typer.Argument(..., help="Label name"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Delete a Label (detaches it from all Issues)."""
    base_url = hiss.client.get_base_url_for_ctx(ctx)
    try:
        with hiss.client.get_client(ctx) as client:
            resp = client.delete(f"/api/v1/labels/{hiss.client.path_segment(name)}")
    except httpx.RequestError as exc:
        hiss.client.handle_request_error(exc, base_url)
    data = hiss.client.handle_response(resp)
    if json_output:
        print_json(data if data is not None else {"name": name, "deleted": True})
    else:
        typer.echo(f"Deleted Label {name}")
