"""Comments command group — thin HTTP mapping."""

import httpx
import typer

import hiss.client
from hiss.output import print_json, print_table

comments_app = typer.Typer(help="Manage Comments")


@comments_app.command("list")
def list_comments(
    ctx: typer.Context,
    issue_id: int = typer.Argument(..., help="Issue ID"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """List Comments of an Issue."""
    base_url = hiss.client.get_base_url_for_ctx(ctx)
    try:
        with hiss.client.get_client(ctx) as client:
            resp = client.get(f"/api/v1/issues/{hiss.client.path_segment(issue_id)}/comments")
    except httpx.RequestError as exc:
        hiss.client.handle_request_error(exc, base_url)
    data = hiss.client.handle_response(resp)
    if json_output:
        print_json(data)
    else:
        if not data:
            typer.echo("No Comments found.")
        else:
            headers = ["id", "body", "created_at"]
            rows = [
                [c.get("id", ""), c.get("body", ""), c.get("created_at", "") or ""] for c in data
            ]
            print_table(headers, rows, title=f"Comments for Issue {issue_id}")


@comments_app.command("add")
def add_comment(
    ctx: typer.Context,
    issue_id: int = typer.Argument(..., help="Issue ID"),
    body: str = typer.Argument(..., help="Comment body"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Add a Comment to an Issue."""
    base_url = hiss.client.get_base_url_for_ctx(ctx)
    payload = {"body": body}
    try:
        with hiss.client.get_client(ctx) as client:
            resp = client.post(
                f"/api/v1/issues/{hiss.client.path_segment(issue_id)}/comments", json=payload
            )
    except httpx.RequestError as exc:
        hiss.client.handle_request_error(exc, base_url)
    data = hiss.client.handle_response(resp)
    if json_output:
        print_json(data)
    else:
        headers = ["id", "body", "created_at"]
        rows = [[data.get("id", ""), data.get("body", ""), data.get("created_at", "") or ""]]
        print_table(headers, rows, title=f"Created Comment for Issue {issue_id}")


@comments_app.command("update")
def update_comment(
    ctx: typer.Context,
    comment_id: int = typer.Argument(..., help="Comment ID"),
    body: str = typer.Option(..., "--body", help="New comment body"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Update a Comment's body."""
    base_url = hiss.client.get_base_url_for_ctx(ctx)
    try:
        with hiss.client.get_client(ctx) as client:
            resp = client.patch(
                f"/api/v1/comments/{hiss.client.path_segment(comment_id)}", json={"body": body}
            )
    except httpx.RequestError as exc:
        hiss.client.handle_request_error(exc, base_url)
    data = hiss.client.handle_response(resp)
    if json_output:
        print_json(data)
    else:
        headers = ["id", "body", "created_at"]
        rows = [[data.get("id", ""), data.get("body", ""), data.get("created_at", "") or ""]]
        print_table(headers, rows, title=f"Updated Comment {comment_id}")


@comments_app.command("delete")
def delete_comment(
    ctx: typer.Context,
    comment_id: int = typer.Argument(..., help="Comment ID"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Delete a Comment."""
    base_url = hiss.client.get_base_url_for_ctx(ctx)
    try:
        with hiss.client.get_client(ctx) as client:
            resp = client.delete(f"/api/v1/comments/{hiss.client.path_segment(comment_id)}")
    except httpx.RequestError as exc:
        hiss.client.handle_request_error(exc, base_url)
    data = hiss.client.handle_response(resp)
    if json_output:
        print_json(data if data is not None else {"id": comment_id, "deleted": True})
    else:
        typer.echo(f"Deleted Comment {comment_id}")
