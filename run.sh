#!/usr/bin/env bash
# Kyvvu-governed coding agent, with and without SHADI.
#
#   ./run.sh setup     install shadictl, create the venv, prepare the two directories
#   ./run.sh demo      run the four scenarios in sequence, pausing between them
#   ./run.sh 1|2|3a|3b run one scenario
#   ./run.sh clean     remove the two directories
#
# Nothing here needs a Kyvvu account or network access after setup.
set -uo pipefail

PKG=$(cd "$(dirname "$0")" && pwd)   # where this script and its files live
AGENT=$PKG/my-agent                  # read-only under SHADI: agent, manifest, venv
OUT=$PKG/agent-out                   # the only directory SHADI lets the agent write to
PY=$AGENT/.venv/bin/python
PYTHON=${PYTHON:-python3}            # interpreter used to create the venv (3.12 or newer)
KYVVU_VERSION=${KYVVU_VERSION:-0.22.1}  # the kyvvu SDK release the outcomes below were verified with

export AGENT_OUT=$OUT
unset KV_API_KEY                     # this demo never talks to the platform

bold() { printf '\n\033[1m%s\033[0m\n' "$*"; }
tree_status() { git -C "$AGENT" status --short | grep -q . && git -C "$AGENT" status --short | sed 's/^/   changed: /' || echo "   agent directory unchanged"; }
restore() { git -C "$AGENT" checkout -q -- .; rm -f "$OUT"/result.txt; }
need() { [ -x "$PY" ] || { echo "run ./run.sh setup first"; exit 1; }; }

setup() {
  command -v shadictl >/dev/null || {
    echo "installing shadictl (https://agntcy.github.io/shadi/install.sh)"
    curl -fsSL https://agntcy.github.io/shadi/install.sh | bash
    export PATH="$HOME/.local/bin:$PATH"
  }
  command -v shadictl >/dev/null || {
    echo "shadictl not on PATH. If the installer could not resolve the latest release, pin it:"
    echo "  SHADI_VERSION=0.2.0 ./run.sh setup"
    exit 1
  }
  mkdir -p "$AGENT" "$OUT"
  cp "$PKG"/agent.py "$PKG"/demo-manifest.yaml "$AGENT"/
  sed "s#__AGENT_DIR__#$AGENT#; s#__OUT_DIR__#$OUT#" "$PKG"/sandbox.json > "$AGENT"/sandbox.json
  [ -x "$PY" ] || { "$PYTHON" -m venv "$AGENT/.venv" && "$AGENT/.venv/bin/pip" install -q "kyvvu==$KYVVU_VERSION"; }
  cd "$AGENT" && git init -q 2>/dev/null; git add -A
  git -c user.name=demo -c user.email=demo@localhost commit -qm pristine 2>/dev/null || true
  echo "ready: $AGENT (read-only under SHADI), $OUT (writable)"
  echo "next: ./run.sh demo"
}

run1() {
  bold "1. Kyvvu allows write_code and run_code; the generated code rewrites agent.py"
  echo "   $ python agent.py tamper"
  (cd "$AGENT" && "$PY" agent.py tamper)
  tree_status; restore
}
run2() {
  bold "2. No approval gate: Kyvvu stops run_code before anything executes"
  echo "   $ python agent.py tamper --no-gate"
  (cd "$AGENT" && "$PY" agent.py tamper --no-gate)
  tree_status
}
run3a() {
  bold "3a. Under SHADI, harmless generated code runs and writes to the output directory"
  echo "   $ shadictl --policy sandbox.json -- python agent.py benign"
  (cd "$OUT" && shadictl --policy "$AGENT/sandbox.json" -- "$PY" "$AGENT/agent.py" benign)
  echo "   result.txt: $(cat "$OUT/result.txt" 2>/dev/null || echo '<missing>')"
  tree_status
}
run3b() {
  bold "3b. Under SHADI, the same tampering code: Kyvvu allows the exec, the kernel refuses the write"
  echo "   $ shadictl --policy sandbox.json -- python agent.py tamper"
  (cd "$OUT" && shadictl --policy "$AGENT/sandbox.json" -- "$PY" "$AGENT/agent.py" tamper)
  tree_status
}

case "${1:-}" in
  setup) setup ;;
  1)  need; run1 ;;
  2)  need; run2 ;;
  3a) need; run3a ;;
  3b) need; run3b ;;
  demo)
    need; restore
    run1;  read -rp "   [enter for 2] "
    run2;  read -rp "   [enter for 3a] "
    run3a; read -rp "   [enter for 3b] "
    run3b
    bold "trace of every run: $OUT/kyvvu-trace.jsonl" ;;
  clean) rm -rf "$AGENT" "$OUT"; echo "removed $AGENT and $OUT" ;;
  *) sed -n '2,9p' "$0"; exit 2 ;;
esac
