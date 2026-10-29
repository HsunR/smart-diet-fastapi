"""Exercise the deployment tail as a script streamed into Bash over stdin."""

import os
from pathlib import Path
import shutil
import subprocess

import pytest
import yaml


def run_deployment(fail_command=""):
    git_bash = Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "Git/bin/bash.exe"
    bash = os.environ.get("BASH_BIN") or (str(git_bash) if git_bash.exists() else shutil.which("bash"))
    if not bash:
        pytest.skip("Bash is required to exercise the SSH deployment script")
    workflow = Path(__file__).resolve().parents[1] / ".github/workflows/deploy-test.yml"
    script = yaml.safe_load(workflow.read_text(encoding="utf-8"))["jobs"]["deploy"]["steps"][0]["run"]
    remote = script.split("<<'REMOTE'\n", 1)[1].rsplit("\nREMOTE", 1)[0]
    tail = remote[remote.index("compose=(docker compose"):]
    # Model Docker attaching to stdin. It must never consume the remaining Bash
    # script. No real Docker, Git state, database or network is touched here.
    harness = r'''
set -Eeuo pipefail
export DEPLOY_SHA=regression-check
docker() {
    printf 'DOCKER %s\n' "$*"
    if [[ -n "${FAIL_COMMAND:-}" && "$*" == *"$FAIL_COMMAND"* ]]; then
        return 17
    fi
    case " $* " in
        *" run "*|*" exec "*) cat > /dev/null ;;
    esac
}
git() { printf '/dev/null\n'; }
'''
    return subprocess.run(
        [bash, "-s"], input=harness + tail + "\n", text=True,
        capture_output=True, timeout=15,
        env=os.environ | {"FAIL_COMMAND": fail_command},
    )


def test_streamed_deployment_reaches_start_reload_and_https_verification():
    result = run_deployment()
    assert result.returncode == 0, result.stderr
    assert " up -d --no-build --wait" in result.stdout
    assert " exec -T caddy caddy reload" in result.stdout
    assert " exec -T app python scripts/check_deployment.py --https" in result.stdout
    assert "Successfully deployed regression-check" in result.stdout


@pytest.mark.parametrize("command", ["caddy-validate", "scripts/check_deployment.py --https"])
def test_deployment_failure_cannot_report_success(command):
    result = run_deployment(command)
    assert result.returncode == 17, result.stdout + result.stderr
    assert "Deployment failed for regression-check" in result.stderr
    assert "Successfully deployed" not in result.stdout
