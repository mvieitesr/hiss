"""Projects command group — thin HTTP mapping."""

import httpx
import typer

import hiss.client
from hiss.output import print_json, print_table

projects_app = typer.Typer(help="Manage Projects")


@projects_app.command("list")
def list_projects(
    ctx: typer.Context,
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """List Projects."""
    base_url = hiss.client.get_base_url_for_ctx(ctx)
    try:
        with hiss.client.get_client(ctx) as client:
            resp = client.get("/api/v1/projects")
    except httpx.RequestError as exc:
        hiss.client.handle_request_error(exc, base_url)
    data = hiss.client.handle_response(resp)
    if json_output:
        print_json(data)
    else:
        if not data:
            typer.echo("No Projects found.")
        else:
            headers = ["id", "key", "name"]
            rows = [[p.get("id", ""), p.get("key", ""), p.get("name", "")] for p in data]
            print_table(headers, rows, title="Projects")


@projects_app.command("create")
def create_project(
    ctx: typer.Context,
    key: str = typer.Option(..., "--key", help="Project key (unique short code)"),
    name: str = typer.Option(..., "--name", help="Project name"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Create a Project."""
    base_url = hiss.client.get_base_url_for_ctx(ctx)
    payload = {"key": key, "name": name}
    try:
        with hiss.client.get_client(ctx) as client:
            resp = client.post("/api/v1/projects", json=payload)
    except httpx.RequestError as exc:
        hiss.client.handle_request_error(exc, base_url)
    data = hiss.client.handle_response(resp)
    if json_output:
        print_json(data)
    else:
        headers = ["id", "key", "name"]
        rows = [[data.get("id", ""), data.get("key", ""), data.get("name", "")]]
        print_table(headers, rows, title="Created Project")


@projects_app.command("delete")
def delete_project(
    ctx: typer.Context,
    key: str = typer.Argument(..., help="Project key"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Delete a Project (cascades its Issues and Comments)."""
    base_url = hiss.client.get_base_url_for_ctx(ctx)
    try:
        with hiss.client.get_client(ctx) as client:
            resp = client.delete(f"/api/v1/projects/{hiss.client.path_segment(key)}")
    except httpx.RequestError as exc:
        hiss.client.handle_request_error(exc, base_url)
    data = hiss.client.handle_response(resp)
    if json_output:
        print_json(data if data is not None else {"key": key, "deleted": True})
    else:
        typer.echo(f"Deleted Project {key}")
