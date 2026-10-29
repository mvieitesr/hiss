"""Issues command group — thin HTTP mapping."""

import httpx
import typer

import hiss.client
from hiss.output import print_json, print_table

issues_app = typer.Typer(help="Manage Issues")


@issues_app.command("list")
def list_issues(
    ctx: typer.Context,
    project: str = typer.Option(..., "--project", help="Project key"),
    status: str = typer.Option(None, "--status", help="Filter by status: open|in_progress|done"),
    priority: str = typer.Option(None, "--priority", help="Filter by priority: low|medium|high"),
    label: str = typer.Option(None, "--label", help="Filter by Label name"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """List Issues of a Project."""
    base_url = hiss.client.get_base_url_for_ctx(ctx)
    params: dict[str, str] = {}
    if status is not None:
        params["status"] = status
    if priority is not None:
        params["priority"] = priority
    if label is not None:
        params["label"] = label
    # If no filters, params stays empty
    try:
        with hiss.client.get_client(ctx) as client:
            resp = client.get(
                f"/api/v1/projects/{hiss.client.path_segment(project)}/issues",
                params=params if params else None,
            )
    except httpx.RequestError as exc:
        hiss.client.handle_request_error(exc, base_url)
    data = hiss.client.handle_response(resp)
    if json_output:
        print_json(data)
    else:
        if not data:
            typer.echo("No Issues found.")
        else:
            headers = ["id", "title", "status", "priority", "labels"]
            rows = []
            for iss in data:
                labels = ", ".join(lb.get("name", "") for lb in (iss.get("labels") or []))
                rows.append(
                    [
                        iss.get("id", ""),
                        iss.get("title", "")[:50],
                        iss.get("status", ""),
                        iss.get("priority", ""),
                        labels,
                    ]
                )
            print_table(headers, rows, title=f"Issues in {project}")


@issues_app.command("create")
def create_issue(
    ctx: typer.Context,
    project: str = typer.Option(..., "--project", help="Project key"),
    title: str = typer.Option(..., "--title", help="Issue title"),
    description: str = typer.Option("", "--description", help="Issue description"),
    priority: str = typer.Option(None, "--priority", help="Priority: low|medium|high"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Create an Issue inside a Project."""
    base_url = hiss.client.get_base_url_for_ctx(ctx)
    payload: dict = {"title": title}
    # Only include optional fields when provided (zero domain logic: send what user gave)
    # description: send if non-empty string (if user passed --description, include; otherwise omit to let API default)
    # But Typer gives "" default, so we need to distinguish: if description != "" then include
    if description:
        payload["description"] = description
    if priority is not None:
        payload["priority"] = priority
    try:
        with hiss.client.get_client(ctx) as client:
            resp = client.post(
                f"/api/v1/projects/{hiss.client.path_segment(project)}/issues", json=payload
            )
    except httpx.RequestError as exc:
        hiss.client.handle_request_error(exc, base_url)
    data = hiss.client.handle_response(resp)
    if json_output:
        print_json(data)
    else:
        headers = ["id", "title", "status", "priority"]
        rows = [
            [
                data.get("id", ""),
                data.get("title", ""),
                data.get("status", ""),
                data.get("priority", ""),
            ]
        ]
        print_table(headers, rows, title="Created Issue")


@issues_app.command("update")
def update_issue(
    ctx: typer.Context,
    issue_id: int = typer.Argument(..., help="Issue ID"),
    status: str = typer.Option(None, "--status", help="New status: open|in_progress|done"),
    priority: str = typer.Option(None, "--priority", help="New priority: low|medium|high"),
    title: str = typer.Option(None, "--title", help="New title"),
    description: str = typer.Option(None, "--description", help="New description"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Update an Issue's status/priority."""
    base_url = hiss.client.get_base_url_for_ctx(ctx)
    payload: dict = {}
    if status is not None:
        payload["status"] = status
    if priority is not None:
        payload["priority"] = priority
    if title is not None:
        payload["title"] = title
    if description is not None:
        payload["description"] = description
    try:
        with hiss.client.get_client(ctx) as client:
            resp = client.patch(
                f"/api/v1/issues/{hiss.client.path_segment(issue_id)}", json=payload
            )
    except httpx.RequestError as exc:
        hiss.client.handle_request_error(exc, base_url)
    data = hiss.client.handle_response(resp)
    if json_output:
        print_json(data)
    else:
        headers = ["id", "title", "status", "priority"]
        rows = [
            [
                data.get("id", ""),
                data.get("title", ""),
                data.get("status", ""),
                data.get("priority", ""),
            ]
        ]
        print_table(headers, rows, title=f"Updated Issue {issue_id}")


@issues_app.command("delete")
def delete_issue(
    ctx: typer.Context,
    issue_id: int = typer.Argument(..., help="Issue ID"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Delete an Issue (cascades its Comments)."""
    base_url = hiss.client.get_base_url_for_ctx(ctx)
    try:
        with hiss.client.get_client(ctx) as client:
            resp = client.delete(f"/api/v1/issues/{hiss.client.path_segment(issue_id)}")
    except httpx.RequestError as exc:
        hiss.client.handle_request_error(exc, base_url)
    data = hiss.client.handle_response(resp)
    if json_output:
        print_json(data if data is not None else {"id": issue_id, "deleted": True})
    else:
        typer.echo(f"Deleted Issue {issue_id}")


@issues_app.command("label")
def label_issue(
    ctx: typer.Context,
    issue_id: int = typer.Argument(..., help="Issue ID"),
    name: str = typer.Argument(..., help="Label name"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Attach a Label to an Issue."""
    base_url = hiss.client.get_base_url_for_ctx(ctx)
    try:
        with hiss.client.get_client(ctx) as client:
            resp = client.post(
                f"/api/v1/issues/{hiss.client.path_segment(issue_id)}/labels/"
                f"{hiss.client.path_segment(name)}"
            )
    except httpx.RequestError as exc:
        hiss.client.handle_request_error(exc, base_url)
    data = hiss.client.handle_response(resp)
    if json_output:
        print_json(data)
    else:
        # API returns {"id": ..., "labels": [{"id":..., "name":...}]}
        labels = ", ".join(lb.get("name", "") for lb in (data.get("labels") or []))
        headers = ["id", "labels"]
        rows = [[data.get("id", issue_id), labels]]
        print_table(headers, rows, title=f"Issue {issue_id} labels")


@issues_app.command("unlabel")
def unlabel_issue(
    ctx: typer.Context,
    issue_id: int = typer.Argument(..., help="Issue ID"),
    name: str = typer.Argument(..., help="Label name"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Detach a Label from an Issue."""
    base_url = hiss.client.get_base_url_for_ctx(ctx)
    try:
        with hiss.client.get_client(ctx) as client:
            resp = client.delete(
                f"/api/v1/issues/{hiss.client.path_segment(issue_id)}/labels/"
                f"{hiss.client.path_segment(name)}"
            )
    except httpx.RequestError as exc:
        hiss.client.handle_request_error(exc, base_url)
    data = hiss.client.handle_response(resp)
    if json_output:
        print_json(data)
    else:
        labels = ", ".join(lb.get("name", "") for lb in (data.get("labels") or []))
        headers = ["id", "labels"]
        rows = [[data.get("id", issue_id), labels]]
        print_table(headers, rows, title=f"Issue {issue_id} labels")
