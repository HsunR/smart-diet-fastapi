#!/usr/bin/env bash
# Keep execution inside main: Bash parses the full function before invoking it.
# This also works when the script arrives on SSH stdin or replaces itself in Git.

usage() {
  cat <<'HELP'
Usage: bash scripts/deploy-test.sh [OPTIONS]

Deploy the current checkout by default; no Git fetch or checkout is performed.
  --check                 Validate Compose only; no daemon, build or startup
  --build-only            Build the API image without updating running services
  --no-build              Deploy using the existing image for this checkout
  --sync                  Fetch and deploy the latest origin/main (clean tree only)
  --revision SHA          With --sync, skip if SHA is no longer origin/main
  --deploy-dir PATH       Repository root (default: script's parent directory)
  --env-file PATH         Environment file relative to the repository (default: .env)
  --wait-timeout SECONDS  Service readiness timeout (default: 120)
  -h, --help              Show this help

Linux/WSL deployment requires Git, Bash, flock, Docker and Compose 2.20+.
Windows Git Bash supports --check with the Docker CLI installed.
No mode deletes data volumes or verifies the separately managed public proxy.
HELP
}

die() { printf 'Deployment stopped: %s\n' "$*" >&2; exit 2; }

main() {
  set -Eeuo pipefail
  local mode=deploy sync=false revision='' deploy_dir='' env_file=.env wait_timeout=120
  while (($#)); do
    case "$1" in
      --check|--build-only|--no-build)
        [[ "$mode" == deploy ]] || die 'Choose only one execution mode.'
        mode="${1#--}"; shift ;;
      --sync) sync=true; shift ;;
      --revision|--deploy-dir|--env-file|--wait-timeout)
        (($# >= 2)) && [[ -n "$2" ]] || die "Missing value for $1"
        case "$1" in
          --revision) revision="$2" ;;
          --deploy-dir) deploy_dir="$2" ;;
          --env-file) env_file="$2" ;;
          --wait-timeout) wait_timeout="$2" ;;
        esac
        shift 2 ;;
      -h|--help) usage; return ;;
      *) die "Unknown option: $1 (see --help)" ;;
    esac
  done
  [[ "$wait_timeout" =~ ^[1-9][0-9]*$ ]] || die 'Timeout must be a positive integer.'
  [[ -z "$revision" || "$revision" =~ ^[0-9a-f]{40}$ ]] || die 'Revision must be a full 40-character SHA.'
  [[ -z "$revision" || "$sync" == true ]] || die '--revision requires --sync.'
  [[ "$mode" != check || "$sync" == false ]] || die '--check does not support --sync.'
  if [[ -z "$deploy_dir" ]]; then
    if [[ -n "${BASH_SOURCE[0]:-}" ]]; then
      deploy_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
    else
      deploy_dir="$PWD"
    fi
  fi
  cd -- "$deploy_dir"
  local command
  for command in git docker; do
    command -v "$command" >/dev/null || die "Required command missing: $command"
  done
  [[ "$(git rev-parse --show-toplevel)" -ef . ]] || die 'Deploy directory must be the Git repository root.'
  export GIT_TERMINAL_PROMPT=0

  if [[ "$mode" != check ]]; then
    command -v flock >/dev/null || die 'flock is required for deployment; use Linux or WSL.'
    # Shared by manual deployment, image builds and Actions on this checkout.
    exec 9> "$(git rev-parse --git-path smartdiet-test-deploy.lock)"
    flock -w 600 9
  fi
  if [[ "$sync" == true ]]; then
    [[ -z "$(git status --porcelain)" ]] || die 'The server checkout has local changes.'
    printf 'Fetching origin/main...\n'
    git -c core.sshCommand='ssh -o BatchMode=yes -o StrictHostKeyChecking=yes' \
      fetch --no-tags origin +refs/heads/main:refs/remotes/origin/main
    local latest
    latest="$(git rev-parse refs/remotes/origin/main)"
    if [[ -n "$revision" && "$revision" != "$latest" ]]; then
      printf 'Skipping outdated deployment %s; main has a newer commit.\n' "$revision"
      return
    fi
    git -c advice.detachedHead=false checkout --detach "$latest"
  fi

  [[ -f "$env_file" && -f docker-compose.test.yml ]] || die 'Missing environment file or docker-compose.test.yml; see README.md.'
  # Ignore inherited DEPLOY_SHA: the tag must describe the actual checkout.
  local checkout_sha
  checkout_sha="$(git rev-parse HEAD)"
  export DEPLOY_SHA="$checkout_sha"
  if [[ -n "$(git status --porcelain)" ]]; then
    export DEPLOY_SHA="local-${checkout_sha:0:12}"
    printf 'Using local worktree image tag %s (includes uncommitted changes).\n' "$DEPLOY_SHA"
  fi
  local -a compose=(docker compose --env-file "$env_file" -f docker-compose.test.yml)
  local stage=configuration
  on_error() {
    local status=$?
    trap - ERR
    printf 'Deployment failed during %s for %s (exit %s).\n' "$stage" "$DEPLOY_SHA" "$status" >&2
    if [[ "$mode" != check ]]; then
      "${compose[@]}" ps --all || true
      "${compose[@]}" logs --no-color --tail 80 app db redis minio || true
    fi
    exit "$status"
  }
  trap on_error ERR
  printf 'Checking Docker Compose configuration...\n'
  docker compose version >/dev/null
  "${compose[@]}" config --quiet
  if [[ "$mode" == check ]]; then
    printf 'Configuration valid; no images built or services started.\n'
    return
  fi
  stage='Docker daemon check'
  docker info >/dev/null
  if [[ "$mode" == no-build ]]; then
    stage='existing image check'
    docker image inspect "smartdiet-test-api:$DEPLOY_SHA" >/dev/null
  else
    stage='image build'
    printf 'Building API image %s...\n' "$DEPLOY_SHA"
    "${compose[@]}" build app
  fi
  if [[ "$mode" == build-only ]]; then
    printf 'Built API image %s; running services unchanged.\n' "$DEPLOY_SHA"
    return
  fi
  stage='service startup and health checks'
  printf 'Starting services; waiting up to %s seconds for readiness...\n' "$wait_timeout"
  "${compose[@]}" up -d --no-build --remove-orphans --wait --wait-timeout "$wait_timeout"
  "${compose[@]}" ps
  local record
  record="$(git rev-parse --git-path smartdiet-test-deployed-sha)"
  printf '%s\n' "$DEPLOY_SHA" > "$record.tmp"
  mv -- "$record.tmp" "$record"
  printf 'Successfully deployed %s to the test server.\n' "$DEPLOY_SHA"
}

# Never let Git/Docker consume the script streamed by SSH.
main "$@" </dev/null
