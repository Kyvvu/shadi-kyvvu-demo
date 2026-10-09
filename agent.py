#!/usr/bin/env python3
"""A Kyvvu-governed coding agent, meant to be launched under SHADI.

The agent has two declared tools:

  * ``write_code`` writes Python source into a scratch file.
  * ``run_code``   executes that file in a subprocess.

That is the agent's job, so the Kyvvu policy set permits it. The generated code
is either harmless (writes a result file) or hostile (appends a line to this
very file). Which of the two runs, and whether it succeeds, is decided by two
independent layers:

  * Kyvvu, in this process, evaluates each declared step against the manifest
    (``demo-manifest.yaml``, one rule: ``step.exec`` requires a preceding
    approval gate).
  * SHADI, outside this process, has restricted what this process tree may
    write on the host. A ``PermissionError`` in the subprocess is the kernel
    refusing.

Usage::

    python agent.py [benign|tamper] [--no-gate]

The policy set is a local file; nothing is fetched. No API key is needed.
Set ``AGENT_OUT`` to the directory the agent may write to (default: ``./out``).
The behavioural trace is appended to ``$AGENT_OUT/kyvvu-trace.jsonl``.
"""

import argparse
import os
import pathlib
import subprocess
import sys

from kyvvu import Kyvvu, KyvvuBlockedError, RiskClassification, StepType, Verb
from kyvvu_engine.io.settings import KyvvuSettings

HERE = pathlib.Path(__file__).resolve().parent
OUT = pathlib.Path(os.environ.get("AGENT_OUT", HERE / "out"))
MANIFEST = HERE / "demo-manifest.yaml"

# What the "LLM" produces. Both snippets are ordinary Python; the agent does not
# inspect them, it only writes them to disk and runs them.
GENERATED_CODE = {
    "benign": (
        f"open({str(OUT / 'result.txt')!r}, 'w').write('42\\n')\n"
        "print('result written')\n"
    ),
    "tamper": (
        f"me = {str(HERE / 'agent.py')!r}\n"
        "open(me, 'a').write('\\n# tampered by generated code\\n')\n"
        "print('agent.py modified')\n"
    ),
}


def build_kernel() -> Kyvvu:
    """Creates the Kyvvu kernel with the local manifest as its policy source.

    ``policy_file`` is passed explicitly (and named in ``explicit_fields``) so
    the SDK treats the file as the configured source even when platform
    credentials happen to be present in the environment. ``fail_mode="closed"``
    stops the agent if the manifest cannot be loaded, rather than running it
    ungoverned.
    """
    settings = KyvvuSettings(
        policy_file=str(MANIFEST),
        agent_key="shadi-coding-demo",
        fail_mode="closed",
        log_location=str(OUT / "kyvvu-trace.jsonl"),
        explicit_fields=frozenset(
            {"policy_file", "agent_key", "fail_mode", "log_location"}
        ),
    )
    return Kyvvu(
        settings=settings,
        agent_id="agent_shadi_coding_demo",  # fixed id: no registration call
        risk_classification=RiskClassification.MINIMAL,
    )


kv = build_kernel()


@kv.step(StepType.step_resource, Verb.POST)
def write_code(path: str, code: str) -> str:
    """Tool: writes generated source to ``path``."""
    pathlib.Path(path).write_text(code)
    return f"wrote {len(code)} bytes to {path}"


@kv.step(StepType.step_exec)
def run_code(path: str) -> str:
    """Tool: runs ``path`` with the current interpreter and returns its output.

    The subprocess inherits whatever host restrictions this process has. Under
    SHADI that means the same Landlock ruleset; no configuration is needed.
    """
    result = subprocess.run(
        [sys.executable, path], capture_output=True, text=True, check=False
    )
    output = (result.stdout + result.stderr).strip()
    return output or f"exit code {result.returncode}"


def record_approval_gate() -> None:
    """Records a human-approval gate so the exec rule is satisfied."""
    kv.add_step(
        StepType.step_gate,
        "human_approval",
        properties={"guard": {"result": "pass"}},
    )


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "mode",
        nargs="?",
        choices=sorted(GENERATED_CODE),
        default="benign",
        help="which generated code to write and execute (default: benign)",
    )
    parser.add_argument(
        "--no-gate",
        action="store_true",
        help="do not record the approval gate before run_code",
    )
    return parser.parse_args(argv)


def step(label: str, detail: str = "") -> None:
    """Prints one line per step the agent takes, so the run reads top to bottom."""
    print(f"   · {label:<20}{detail}")


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    OUT.mkdir(parents=True, exist_ok=True)
    scratch = str(OUT / "scratch.py")

    kv.start_task()
    step("task.start", f"mode={args.mode}, gate={'skipped' if args.no_gate else 'recorded'}")
    try:
        step("step.resource POST", "write_code")
        print("  ", write_code(scratch, GENERATED_CODE[args.mode]))
        if not args.no_gate:
            record_approval_gate()
            step("step.gate", "human_approval (guard: pass)")
        else:
            step("step.gate", "— skipped, so the next step has no approval")
        step("step.exec", "run_code")
        print("   run_code ->", run_code(scratch))
    except KyvvuBlockedError as exc:
        # The kernel has already closed the task with a task.error record.
        step("task.error", "Kyvvu refused the step below")
        print(f"   Kyvvu blocked: {exc}")
        return 1
    except Exception as exc:  # pylint: disable=broad-except
        kv.error_task(error=exc)
        raise
    step("task.end")
    kv.end_task()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
