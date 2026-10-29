"""Manual integration checks for an isolated, running blue-green demo."""

import json
import os
import shlex
import shutil
import subprocess
from pathlib import Path


DEMO = Path(__file__).resolve().parents[1]
COMPOSE = ["docker", "compose", "-f", str(DEMO / "compose.yml")]


def run(*args, check=True):
    return subprocess.run(args, check=check, capture_output=True, text=True, env=os.environ)


def curl_fault_env(tmp_path, fail_at, version="audit-injected-mismatch"):
    shim = tmp_path / "curl"
    shim.write_text(
        "#!/bin/sh\n"
        'for arg do case "$arg" in */version)\n'
        '  count=0; [ ! -f "$CURL_COUNT" ] || count=$(cat "$CURL_COUNT")\n'
        '  count=$((count + 1)); echo "$count" > "$CURL_COUNT"\n'
        '  if [ "$CURL_FAIL_AT" -eq 0 ] || [ "$count" -eq "$CURL_FAIL_AT" ]; then\n'
        f"    printf '%s\\n' {shlex.quote(json.dumps({'version': version}))}; exit 0\n"
        "  fi;; esac; done\n"
        f'exec {shlex.quote(shutil.which("curl"))} "$@"\n'
    )
    shim.chmod(0o755)
    env = os.environ.copy()
    env.update(
        PATH=f"{tmp_path}:{env['PATH']}",
        CURL_COUNT=str(tmp_path / "curl.count"),
        CURL_FAIL_AT=str(fail_at),
    )
    return env


def health(service):
    container = run(*COMPOSE, "ps", "-q", service).stdout.strip()
    return run("docker", "inspect", "--format", "{{.State.Health.Status}}", container).stdout.strip()


def test_proxy_is_healthy():
    assert health("proxy") == "healthy"


def test_slots_wait_for_a_single_migration_job():
    config = json.loads(run(*COMPOSE, "config", "--format", "json").stdout)
    services = config["services"]
    assert "migrate" in services
    for slot in ("blue", "green"):
        assert services[slot]["depends_on"]["migrate"]["condition"] == "service_completed_successfully"
        assert services[slot]["entrypoint"][0] == "gunicorn"
    assert services["migrate"]["entrypoint"][0] == "alembic"


def test_status_uses_proxy_configuration():
    run(str(DEMO / "switch.sh"), "switch", "green")
    run(
        *COMPOSE,
        "exec",
        "-T",
        "proxy",
        "sh",
        "-c",
        "ACTIVE_SLOT=blue envsubst '${ACTIVE_SLOT}' < /etc/nginx/templates/nginx.conf.template "
        "> /etc/nginx/conf.d/default.conf && nginx -s reload",
    )
    assert "Active slot: blue" in run(str(DEMO / "switch.sh"), "status").stdout
    run(str(DEMO / "switch.sh"), "switch", "green")
    assert "Active slot: green" in run(str(DEMO / "switch.sh"), "status").stdout


def test_script_requires_password_for_compose():
    env = os.environ.copy()
    env.pop("POSTGRES_PASSWORD", None)
    result = subprocess.run(
        [str(DEMO / "switch.sh"), "status"], capture_output=True, text=True, env=env
    )
    assert result.returncode != 0
    assert "Error: POSTGRES_PASSWORD must be set" in result.stderr


def test_demo_requires_password_for_compose():
    env = os.environ.copy()
    env.pop("POSTGRES_PASSWORD", None)
    result = subprocess.run(
        [str(DEMO / "demo-check.sh")], capture_output=True, text=True, env=env
    )
    assert result.returncode != 0
    assert "Error: POSTGRES_PASSWORD must be set" in result.stderr


def test_deploy_rejects_wrong_version(tmp_path):
    result = subprocess.run(
        [str(DEMO / "switch.sh"), "deploy", "0.1.0-snapshot"],
        capture_output=True,
        text=True,
        env=curl_fault_env(tmp_path, 2),
    )
    assert "audit-injected-mismatch" in result.stdout
    assert result.returncode != 0


def test_demo_rejects_wrong_rollback_version(tmp_path):
    result = subprocess.run(
        [str(DEMO / "demo-check.sh")],
        capture_output=True,
        text=True,
        env=curl_fault_env(tmp_path, 6),
    )
    assert "audit-injected-mismatch" in result.stdout
    assert result.returncode != 0


def test_demo_rejects_empty_switch_version(tmp_path):
    before = run(str(DEMO / "switch.sh"), "status").stdout.splitlines()[0]
    result = subprocess.run(
        [str(DEMO / "demo-check.sh")],
        capture_output=True,
        text=True,
        env=curl_fault_env(tmp_path, 4, version=""),
    )
    assert result.returncode != 0
    assert run(str(DEMO / "switch.sh"), "status").stdout.splitlines()[0] == before


def test_rollback_rejects_wrong_version(tmp_path):
    result = subprocess.run(
        [str(DEMO / "switch.sh"), "rollback"],
        capture_output=True,
        text=True,
        env=curl_fault_env(tmp_path, 0),
    )
    assert "audit-injected-mismatch" in result.stdout
    assert result.returncode != 0


def test_demo_preserves_deployed_slots():
    run(str(DEMO / "switch.sh"), "deploy", "0.1.0-snapshot")
    before = {slot: run(*COMPOSE, "ps", "-q", slot).stdout for slot in ("blue", "green")}
    result = run(str(DEMO / "demo-check.sh"))
    after = {slot: run(*COMPOSE, "ps", "-q", slot).stdout for slot in ("blue", "green")}
    assert before == after
    assert f"Project: {os.environ['COMPOSE_PROJECT_NAME']}" in result.stdout


def test_demo_requires_healthy_proxy(tmp_path):
    docker = tmp_path / "docker"
    docker_bin = shlex.quote(shutil.which("docker"))
    docker.write_text(
        "#!/bin/sh\n"
        'if [ "$1" = inspect ]; then\n'
        '  for last do :; done\n'
        f'  name=$({docker_bin} inspect --format \'{{{{.Name}}}}\' "$last" 2>/dev/null)\n'
        '  case "$name" in */*proxy-1) echo unhealthy; exit 0;; esac\n'
        "fi\n"
        f'exec {docker_bin} "$@"\n'
    )
    docker.chmod(0o755)
    env = os.environ.copy()
    env["PATH"] = f"{tmp_path}:{env['PATH']}"
    result = subprocess.run([str(DEMO / "demo-check.sh")], capture_output=True, text=True, env=env)
    assert result.returncode != 0
    assert "proxy" in result.stdout or "proxy" in result.stderr


def test_active_slot_survives_proxy_recreation():
    run(str(DEMO / "switch.sh"), "switch", "green")
    run(*COMPOSE, "up", "-d", "--no-deps", "--force-recreate", "proxy")
    config = run(*COMPOSE, "exec", "-T", "proxy", "cat", "/etc/nginx/conf.d/default.conf").stdout
    assert "proxy_pass http://green:8000;" in config
    assert "Active slot: green" in run(str(DEMO / "switch.sh"), "status").stdout
