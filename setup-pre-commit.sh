#!/usr/bin/env bash
# Install repository pre-commit checks into an isolated local environment.
set -euo pipefail

PIP_MIRROR="${PIP_MIRROR:-https://mirrors.aliyun.com/pypi/simple/}"
VENV_DIR=".pre-commit-venv"
PRE_COMMIT_VERSION="4.6.1"
MYPY_VERSION="1.19.1"

log() { printf '\033[1;32m[setup]\033[0m %s\n' "$*"; }
die() { printf '\033[1;31m[error]\033[0m %s\n' "$*" >&2; exit 1; }

command -v git >/dev/null 2>&1 || die "git is required"
git rev-parse --show-toplevel >/dev/null 2>&1 \
  || die "run this script inside the repository"
REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "$REPO_ROOT"
[ -f .pre-commit-config.yaml ] || die ".pre-commit-config.yaml not found"

PYTHON=""
for candidate in python3.13 python3.12 python3.11 python3.10 python3; do
  if ! command -v "$candidate" >/dev/null 2>&1; then
    continue
  fi
  version="$("$candidate" -c \
    'import sys; print("%d.%d" % sys.version_info[:2])' 2>/dev/null || echo 0.0)"
  major="${version%%.*}"
  minor="${version##*.}"
  if [ "${major:-0}" -eq 3 ] && [ "${minor:-0}" -ge 10 ]; then
    PYTHON="$candidate"
    break
  fi
done
[ -n "$PYTHON" ] || die "Python 3.10 or newer is required for tooling"

PIP_ARGS=(-i "$PIP_MIRROR")
PIP_HOST="${PIP_MIRROR#*://}"
PIP_HOST="${PIP_HOST%%/*}"
if [[ "$PIP_MIRROR" == http://* ]]; then
  PIP_ARGS+=(--trusted-host "$PIP_HOST")
fi

log "tooling Python: $PYTHON ($("$PYTHON" --version 2>&1))"
log "temporary pip mirror: $PIP_MIRROR"

if [ ! -d "$VENV_DIR" ]; then
  log "create isolated environment: $VENV_DIR/"
  "$PYTHON" -m venv "$VENV_DIR" \
    || die "failed to create the virtual environment"
fi

VENV_PY="$VENV_DIR/bin/python"
[ -x "$VENV_PY" ] \
  || die "$VENV_DIR is incomplete; remove it and run this script again"

log "install pinned pre-commit tools"
"$VENV_PY" -m pip install --disable-pip-version-check \
  "${PIP_ARGS[@]}" \
  "pre-commit==$PRE_COMMIT_VERSION" \
  "flake8==7.3.0" \
  "codespell==2.4.1" \
  "bandit[toml]==1.9.4" \
  "mypy==$MYPY_VERSION"

PRE_COMMIT="$VENV_DIR/bin/pre-commit"
"$PRE_COMMIT" validate-config .pre-commit-config.yaml

log "install git hook"
"$PRE_COMMIT" install

log "pre-install hook environments"
if [[ "$PIP_MIRROR" == http://* ]]; then
  PIP_INDEX_URL="$PIP_MIRROR" PIP_TRUSTED_HOST="$PIP_HOST" \
    "$PRE_COMMIT" install-hooks
else
  PIP_INDEX_URL="$PIP_MIRROR" "$PRE_COMMIT" install-hooks
fi

log "done; future git commit commands will run the checks automatically"
log "manual run: $PRE_COMMIT run --files <file>"
log "uninstall:  $PRE_COMMIT uninstall, then remove $VENV_DIR/"
