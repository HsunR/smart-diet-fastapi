"""Exercise the shared deployment script without Docker, SSH or a real checkout."""

import os
from pathlib import Path
import shutil
import subprocess

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[1]
SHA = "a" * 40


@pytest.fixture
def bash():
    git_bash = Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "Git/bin/bash.exe"
    value = os.environ.get("BASH_BIN") or (str(git_bash) if git_bash.exists() else shutil.which("bash"))
    if not value:
        pytest.skip("Bash is required for deployment script tests")
    return value


@pytest.fixture
def deployment(tmp_path, bash):
    directory = tmp_path / "deploy repo"
    directory.mkdir()
    (directory / ".git").mkdir()
    (directory / ".env").write_text("", encoding="utf-8")
    (directory / "docker-compose.test.yml").write_text("services: {}\n", encoding="utf-8")
    script = ROOT.joinpath("scripts/deploy-test.sh").read_text(encoding="utf-8")
    script_file = directory / "deploy-test.sh"
    script_file.write_text(script, encoding="utf-8")
    record = directory / ".git/smartdiet-test-deployed-sha"
    record.write_text("previous-version\n", encoding="utf-8")
    # Every external operation is stubbed. Deliberately read stdin in Docker and
    # Git fetch to reproduce the old SSH-stream truncation failure if unprotected.
    harness = r'''
docker() {
    printf 'DOCKER %s\n' "$*"
    if [[ "$*" == 'image inspect '* ]]; then printf 'DOCKER %s\n' "$*" >&2; fi
    if [[ -n "${FAIL_COMMAND:-}" && "$*" == *"$FAIL_COMMAND"* ]]; then return 17; fi
    cat >/dev/null
}
flock() { printf 'LOCK %s\n' "$*"; }
git() {
    case "$*" in
        'rev-parse --show-toplevel') pwd ;;
        'rev-parse --git-path '*) printf '.git/%s\n' "$3" ;;
        'rev-parse HEAD') printf '%s\n' "$CHECKOUT_SHA" ;;
        'rev-parse refs/remotes/origin/main') printf '%s\n' "$LATEST_SHA" ;;
        'status --porcelain') if [[ "$DIRTY" == 1 ]]; then printf ' M file\n'; fi ;;
        *' fetch '*) printf 'FETCH\n'; cat >/dev/null ;;
        *' checkout '*) printf 'CHECKOUT\n' ;;
        *) printf 'Unexpected Git command: %s\n' "$*" >&2; return 99 ;;
    esac
}
'''

    def run(*args, streamed=True, failure="", dirty=False, latest=SHA):
        env = os.environ | {"FAIL_COMMAND": failure, "DIRTY": "1" if dirty else "0", "CHECKOUT_SHA": SHA, "LATEST_SHA": latest, "DEPLOY_SHA": "inherited-stale-tag"}
        if streamed:
            command = [bash, "-s", "--", "--deploy-dir", str(directory), *args]
            source = harness + script
        else:
            command = [bash, "-c", harness + '\nsource "$1" "${@:2}"', "test", str(script_file), "--deploy-dir", str(directory), *args]
            source = ""
        result = subprocess.run(command, input=source, text=True, capture_output=True, timeout=15, env=env)
        return result, record.read_text(encoding="utf-8").strip()

    return run


@pytest.mark.parametrize("streamed", [False, True])
def test_file_and_ssh_stream_reach_startup_and_record_success(deployment, streamed):
    result, record = deployment(streamed=streamed)
    assert result.returncode == 0, result.stdout + result.stderr
    assert " up -d --no-build --remove-orphans --wait" in result.stdout
    assert f"Successfully deployed {SHA}" in result.stdout
    assert record == SHA


def test_check_never_uses_daemon_lock_build_or_services(deployment):
    result, record = deployment("--check", dirty=True)
    assert result.returncode == 0, result.stderr
    assert "Configuration valid" in result.stdout
    for operation in ("LOCK", "DOCKER info", " build app", " up -d"):
        assert operation not in result.stdout
    assert record == "previous-version"


def test_build_only_leaves_services_and_deployed_record_untouched(deployment):
    result, record = deployment("--build-only")
    assert result.returncode == 0, result.stderr
    assert " build app" in result.stdout and " up -d" not in result.stdout
    assert "Successfully deployed" not in result.stdout
    assert record == "previous-version"


def test_no_build_reuses_the_checkout_image(deployment):
    result, record = deployment("--no-build", "--wait-timeout", "300")
    assert result.returncode == 0, result.stderr
    assert f"image inspect smartdiet-test-api:{SHA}" in result.stderr
    assert " build app" not in result.stdout
    assert "--wait-timeout 300" in result.stdout
    assert record == SHA


@pytest.mark.parametrize("mode,command", [((), "config --quiet"), ((), "build app"), ((), "up -d"), (("--no-build",), "image inspect")])
def test_failures_preserve_previous_record_and_do_not_report_success(deployment, mode, command):
    result, record = deployment(*mode, failure=command)
    assert result.returncode == 17, result.stdout + result.stderr
    assert "Deployment failed during" in result.stderr
    assert "Successfully deployed" not in result.stdout
    if command != "up -d":
        assert " up -d" not in result.stdout
    assert record == "previous-version"


def test_sync_reads_all_steps_before_git_fetch_and_deploys(deployment):
    result, record = deployment("--sync", "--revision", SHA)
    assert result.returncode == 0, result.stderr
    assert "FETCH" in result.stdout and "CHECKOUT" in result.stdout
    assert f"Successfully deployed {SHA}" in result.stdout
    assert record == SHA


def test_sync_rejects_dirty_checkout_without_fetching(deployment):
    result, record = deployment("--sync", dirty=True)
    assert result.returncode != 0
    assert "local changes" in result.stderr
    assert "FETCH" not in result.stdout and " up -d" not in result.stdout
    assert record == "previous-version"


def test_old_actions_revision_is_skipped_before_build_or_checkout(deployment):
    result, record = deployment("--sync", "--revision", "b" * 40)
    assert result.returncode == 0, result.stderr
    assert "Skipping outdated deployment" in result.stdout
    assert "CHECKOUT" not in result.stdout and " build app" not in result.stdout
    assert record == "previous-version"


def test_local_changes_are_not_recorded_as_a_clean_commit(deployment):
    result, record = deployment(dirty=True)
    assert result.returncode == 0, result.stderr
    assert record == "local-" + SHA[:12]


@pytest.mark.parametrize("args", [("--check", "--sync"), ("--wait-timeout", "0"), ("--revision", SHA), ("--no-build", "--check")])
def test_invalid_options_do_not_start_services(deployment, args):
    result, record = deployment(*args)
    assert result.returncode != 0
    assert " up -d" not in result.stdout
    assert record == "previous-version"


def test_workflow_streams_shared_script_instead_of_inline_deploy_logic(bash):
    workflow = yaml.safe_load(ROOT.joinpath(".github/workflows/deploy-test.yml").read_text(encoding="utf-8"))
    steps = workflow["jobs"]["deploy"]["steps"]
    script = next(step["run"] for step in steps if "run" in step)
    assert "< scripts/deploy-test.sh" in script
    assert "--sync --revision" in script
    assert "docker compose" not in script and "<<'REMOTE'" not in script
    result = subprocess.run([bash, "-n"], input=script, text=True, capture_output=True)
    assert result.returncode == 0, result.stderr
