"""Contracts for the deployment workflows, exercised without GitHub or deployments."""

import os
import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def workflow(name):
    return yaml.safe_load((ROOT / ".github" / "workflows" / name).read_text())


def step(name, job, step_name):
    return next(s for s in workflow(name)["jobs"][job]["steps"] if s["name"] == step_name)


def run_script(script, *, env=None, functions=""):
    return subprocess.run(
        ["bash", "-c", f"{functions}\n{script}"],
        env={**os.environ, **(env or {})},
        text=True,
        capture_output=True,
        timeout=10,
    )


def test_release_gate_rejects_ci_only_from_a_pull_request():
    functions = r"""
        git() { return 0; }
        sleep() { :; }
        gh() {
          if [[ "$*" == *"--event push"* && "$*" == *"--branch main"* ]]; then
            printf 'null:null\n'
          else
            printf 'completed:success\n'
          fi
        }
    """
    for name in ("cd-staging.yml", "cd-prod.yml"):
        script = step(name, "ci-gate", "Wait for CI success on this commit")["run"]
        result = run_script(
            script,
            env={"GITHUB_SHA": "a" * 40, "GITHUB_REPOSITORY": "Student/hiss"},
            functions=functions,
        )
        assert result.returncode != 0, f"{name} accepted PR-only CI"


def test_release_gate_accepts_successful_main_push():
    functions = r"""
        git() { [[ "$*" == "merge-base --is-ancestor $GITHUB_SHA origin/main" ]]; }
        gh() {
          [[ "$*" == *"--event push"* && "$*" == *"--branch main"* && "$*" == *"--commit $GITHUB_SHA"* ]] || return 1
          printf 'completed:success\n'
        }
    """
    for name in ("cd-staging.yml", "cd-prod.yml"):
        script = step(name, "ci-gate", "Wait for CI success on this commit")["run"]
        result = run_script(
            script,
            env={"GITHUB_SHA": "a" * 40, "GITHUB_REPOSITORY": "Student/hiss"},
            functions=functions,
        )
        assert result.returncode == 0, result.stderr


def test_release_gate_requires_commit_reachable_from_main():
    functions = r"""
        git() { return 1; }
        gh() { printf 'completed:success\n'; }
    """
    for name in ("cd-staging.yml", "cd-prod.yml"):
        script = step(name, "ci-gate", "Wait for CI success on this commit")["run"]
        result = run_script(
            script,
            env={"GITHUB_SHA": "a" * 40, "GITHUB_REPOSITORY": "Student/hiss"},
            functions=functions,
        )
        assert result.returncode != 0, f"{name} accepted a commit outside main"
        assert "main" in result.stderr


def test_rollback_and_cd_share_environment_lock():
    rollback = workflow("rollback.yml")["concurrency"]["group"]
    for environment in ("dev", "staging", "prod"):
        group = workflow(f"cd-{environment}.yml")["concurrency"]["group"]
        assert rollback.replace("${{ inputs.environment }}", environment) == group


def test_runtime_requirements_exclude_test_tools():
    runtime = (ROOT / "app/requirements.txt").read_text().lower()
    dev_path = ROOT / "app/requirements-dev.txt"
    assert "pytest" not in runtime
    assert dev_path.exists()
    assert "pytest" in dev_path.read_text().lower()
    assert "pytest.ini" in (ROOT / "app/.dockerignore").read_text()
    ci = workflow("ci.yml")["jobs"]["test-app"]["steps"]
    assert "app/requirements-dev.txt" in next(
        s["run"] for s in ci if s["name"] == "Install app dependencies"
    )


def test_image_recipe_records_source_revision_and_version():
    dockerfile = (ROOT / "app/Dockerfile").read_text()
    for key in ("revision", "source", "version"):
        assert f"org.opencontainers.image.{key}" in dockerfile
    assert "ARG VCS_REF" in dockerfile
    build = step("_build-push.yml", "build", "Build and push image")["with"]
    assert "VCS_REF=" in build["build-args"]
    assert "SOURCE_URL=" in build["build-args"]
    assert "IMAGE_VERSION=" in build["build-args"]


def test_image_base_is_pinned_to_a_variant_and_digest():
    dockerfile = (ROOT / "app/Dockerfile").read_text()
    assert "FROM python:3.13-slim-trixie@sha256:" in dockerfile


def test_dev_requires_explicit_sha_tag_and_version():
    env = {**os.environ, "POSTGRES_PASSWORD": "dummy"}
    for key in ("IMAGE_TAG", "APP_VERSION"):
        env.pop(key, None)
    command = [
        "docker",
        "compose",
        "-f",
        "deploy/compose.yml",
        "--env-file",
        "deploy/dev.env",
        "-p",
        "hiss-fix-pipe",
        "config",
        "-q",
    ]
    missing = subprocess.run(command, cwd=ROOT, env=env, text=True, capture_output=True)
    assert missing.returncode != 0
    assert "IMAGE_TAG" in missing.stderr
    env["IMAGE_TAG"] = "789749c4"
    missing_version = subprocess.run(command, cwd=ROOT, env=env, text=True, capture_output=True)
    assert missing_version.returncode != 0
    assert "APP_VERSION" in missing_version.stderr
    env["APP_VERSION"] = "789749c4"
    assert subprocess.run(command, cwd=ROOT, env=env, capture_output=True).returncode == 0


def test_fork_publishes_to_lowercase_owner(tmp_path):
    script = step("_build-push.yml", "build", "Resolve image")["run"]
    output = tmp_path / "output"
    result = run_script(
        script, env={"GITHUB_REPOSITORY_OWNER": "Student-A", "GITHUB_OUTPUT": str(output)}
    )
    assert result.returncode == 0, result.stderr
    assert "image=ghcr.io/student-a/hiss\n" in output.read_text()
    build = step("_build-push.yml", "build", "Build and push image")["with"]
    assert "steps.image.outputs.image" in build["tags"]


def test_release_promotes_published_digest_without_building(tmp_path):
    reusable = workflow("_build-push.yml")
    script = step("_build-push.yml", "build", "Promote existing image")["run"]
    output = tmp_path / "output"
    calls = tmp_path / "calls"
    digest = "sha256:" + "a" * 64
    functions = r"""
        docker() {
          printf '%s\n' "$*" >> "$MOCK_CALLS"
          case "$*" in
            *"imagetools inspect"*"json .Image"*) printf '{"config":{"Labels":{"org.opencontainers.image.revision":"%s"}}}\n' "$COMMIT_SHA" ;;
            *"imagetools inspect"*) printf '%s\n' "$MOCK_DIGEST" ;;
            *"imagetools create"*) return 0 ;;
            *) return 1 ;;
          esac
        }
    """
    env = {
        "IMAGE": "ghcr.io/student/hiss",
        "SOURCE_TAG": "789749c4",
        "RELEASE_TAG": "1.2.3",
        "GITHUB_OUTPUT": str(output),
        "MOCK_CALLS": str(calls),
        "MOCK_DIGEST": digest,
        "COMMIT_SHA": "789749c4" + "0" * 32,
    }
    result = run_script(script, env=env, functions=functions)
    assert result.returncode == 0, result.stderr
    assert f"digest={digest}\n" in output.read_text()
    commands = calls.read_text()
    assert f"ghcr.io/student/hiss@{digest}" in commands
    assert "--tag ghcr.io/student/hiss:1.2.3" in commands
    assert " build " not in commands
    assert "digest" in reusable[True]["workflow_call"]["outputs"]
    assert "source_tag == ''" in step("_build-push.yml", "build", "Build and push image")["if"]
    for name in ("cd-staging.yml", "cd-prod.yml"):
        job = workflow(name)["jobs"]["build"]
        assert "needs.prepare.outputs.sha8" in job["with"]["source_tag"]
        assert "github.sha" in job["with"]["ref"]


def test_release_fails_clearly_if_commit_image_is_missing(tmp_path):
    script = step("_build-push.yml", "build", "Promote existing image")["run"]
    result = run_script(
        script,
        env={
            "IMAGE": "ghcr.io/student/hiss",
            "SOURCE_TAG": "789749c4",
            "RELEASE_TAG": "1.2.3",
            "COMMIT_SHA": "789749c4" + "0" * 32,
            "GITHUB_OUTPUT": str(tmp_path / "output"),
        },
        functions="docker() { return 1; }",
    )
    assert result.returncode != 0
    assert "789749c4" in result.stderr
    assert "not found" in result.stderr.lower()


def test_release_rejects_changed_promoted_digest(tmp_path):
    script = step("_build-push.yml", "build", "Promote existing image")["run"]
    functions = r"""
        docker() {
          case "$*" in
            *"json .Image"*) printf '{"config":{"Labels":{"org.opencontainers.image.revision":"%s"}}}\n' "$COMMIT_SHA" ;;
            *"inspect"*":1.2.3"*) printf 'sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb\n' ;;
            *"inspect"*) printf 'sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\n' ;;
            *"create"*) return 0 ;;
          esac
        }
    """
    result = run_script(
        script,
        env={
            "IMAGE": "ghcr.io/student/hiss",
            "SOURCE_TAG": "789749c4",
            "RELEASE_TAG": "1.2.3",
            "COMMIT_SHA": "789749c4" + "0" * 32,
            "GITHUB_OUTPUT": str(tmp_path / "output"),
        },
        functions=functions,
    )
    assert result.returncode != 0
    assert "differs from source" in result.stderr


def test_release_rejects_sha8_collision_or_unlabelled_image(tmp_path):
    script = step("_build-push.yml", "build", "Promote existing image")["run"]
    functions = r"""
        docker() {
          case "$*" in
            *"imagetools inspect"*"json .Image"*) printf '{"config":{"Labels":{"org.opencontainers.image.revision":"wrong"}}}\n' ;;
            *"imagetools inspect"*) printf '%s\n' "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa" ;;
            *"imagetools create"*) printf 'unexpected promotion\n' ;;
          esac
        }
    """
    result = run_script(
        script,
        env={
            "IMAGE": "ghcr.io/student/hiss",
            "SOURCE_TAG": "789749c4",
            "RELEASE_TAG": "1.2.3",
            "COMMIT_SHA": "789749c4" + "0" * 32,
            "GITHUB_OUTPUT": str(tmp_path / "output"),
        },
        functions=functions,
    )
    assert result.returncode != 0
    assert "revision" in result.stderr.lower()
    assert "unexpected promotion" not in result.stdout


def test_cd_deploys_owner_image_by_published_digest():
    digest = "sha256:" + "a" * 64
    for environment in ("dev", "staging", "prod"):
        name = f"cd-{environment}.yml"
        job = workflow(name)["jobs"]["deploy"]
        assert "needs.build.outputs.image" in job["env"]["IMAGE"]
        assert "needs.build.outputs.digest" in job["env"]["DIGEST"]
        for action in ("Pull", "Start"):
            script = step(
                name,
                "deploy",
                f"{action} {environment} {'image' if action == 'Pull' else 'services'}",
            )["run"]
            result = run_script(
                script,
                env={
                    "IMAGE": "ghcr.io/student/hiss",
                    "DIGEST": digest,
                    "DEPLOY_TAG": "1.2.3",
                    "POSTGRES_PASSWORD": "dummy",
                },
                functions='docker() { printf "%s:%s version=%s %s\\n" "$IMAGE" "$IMAGE_TAG" "$APP_VERSION" "$*"; }',
            )
            assert result.returncode == 0, result.stderr
            assert f"ghcr.io/student/hiss:1.2.3@{digest} version=1.2.3" in result.stdout
            if action == "Start":
                assert "--no-build" in result.stdout and "--pull never" in result.stdout


def test_rollback_uses_owner_image(tmp_path):
    script = step("rollback.yml", "deploy", "Resolve image")["run"]
    env_file = tmp_path / "env"
    result = run_script(
        script, env={"GITHUB_REPOSITORY_OWNER": "Student-A", "GITHUB_ENV": str(env_file)}
    )
    assert result.returncode == 0, result.stderr
    assert "IMAGE=ghcr.io/student-a/hiss\n" in env_file.read_text()


def test_ci_validates_all_workflows_and_environment_configs():
    job = workflow("ci.yml")["jobs"]["lint-pipeline"]
    assert "actionlint" in next(s["run"] for s in job["steps"] if s["name"] == "Validate workflows")
    script = next(s["run"] for s in job["steps"] if s["name"] == "Validate Compose configurations")
    result = run_script(script, functions='docker() { printf "%s\\n" "$*"; }')
    assert result.returncode == 0, result.stderr
    for environment in ("dev", "staging", "prod"):
        assert f"deploy/{environment}.env" in result.stdout
    filters = step("ci.yml", "changes", "Filter changed paths")["with"]["filters"]
    assert ".github/workflows/**" in filters and "deploy/**" in filters and "compose.yml" in filters


def test_cd_limits_package_writes_and_actions_reads_to_required_jobs():
    for environment in ("dev", "staging", "prod"):
        data = workflow(f"cd-{environment}.yml")
        assert data["permissions"] == {}
        assert data["jobs"]["build"]["permissions"]["packages"] == "write"
        assert "secrets" not in data["jobs"]["build"]
        assert data["jobs"]["deploy"]["permissions"] == {"contents": "read"}
        if environment != "dev":
            assert data["jobs"]["ci-gate"]["permissions"] == {"contents": "read", "actions": "read"}
    ci = workflow("ci.yml")
    assert "pull-requests" not in ci["permissions"]
    assert ci["jobs"]["changes"]["permissions"]["pull-requests"] == "read"
