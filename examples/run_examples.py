"""Runs the three Kyvvu policies in this directory and checks each outcome.

    ./run.sh examples

Each case builds a Kyvvu kernel from one policy file, declares a few steps
through the same ``@kv.step`` decorator ``agent.py`` uses, and compares what
Kyvvu permitted and refused with what is expected. The tools here do nothing:
only the declared steps and their order matter. No SHADI, no network, no
Kyvvu account.
"""

import logging
import pathlib
import sys
import tempfile

import scoped_rule  # noqa: F401  registers the rule input_equals_history_output
from kyvvu import ActionKind, Kyvvu, KyvvuBlockedError, RiskClassification, Verb
from kyvvu_engine import KyvvuSettings

logging.disable(logging.INFO)  # print the outcomes below, not the engine's INFO lines

HERE = pathlib.Path(__file__).resolve().parent
failures = []


def kernel(policy_file: str) -> Kyvvu:
    """A Kyvvu kernel that loads one policy file and writes its trace to a temp dir."""
    settings = KyvvuSettings(
        policy_file=str(HERE / policy_file),
        agent_key="shadi-demo-examples",
        fail_mode="closed",
        log_location=str(pathlib.Path(tempfile.mkdtemp()) / "kyvvu-trace.jsonl"),
        explicit_fields=frozenset(
            {"policy_file", "agent_key", "fail_mode", "log_location"}
        ),
    )
    return Kyvvu(
        settings=settings,
        agent_id="agent_shadi_demo_examples",
        risk_classification=RiskClassification.MINIMAL,
    )


def check(label: str, call, expected: str) -> None:
    """Run one declared step and compare the outcome with ``expected``."""
    try:
        call()
        outcome = "permitted"
    except KyvvuBlockedError:
        outcome = "refused"
    mark = "ok" if outcome == expected else "UNEXPECTED"
    print(f"   {outcome:<10} {label}   [{mark}]")
    if outcome != expected:
        failures.append(label)


def title(text: str) -> None:
    print(f"\n\033[1m{text}\033[0m")


# 1. Individually allowed steps that leak together (GitHub MCP, Invariant Labs).
title("1. no-external-write-after-confidential-read.yaml")
kv = kernel("no-external-write-after-confidential-read.yaml")


@kv.step(ActionKind.step_resource, Verb.GET, properties={"target": {"trust": "external"}})
def read_public_issue() -> str:
    return "issue text"


@kv.step(ActionKind.step_resource, Verb.GET, properties={"data": {"classification": "confidential"}})
def read_private_repo() -> str:
    return "private data"


@kv.step(ActionKind.step_resource, Verb.POST, properties={"target": {"trust": "internal"}})
def write_private_repo() -> str:
    return "committed"


@kv.step(ActionKind.step_resource, Verb.POST, properties={"target": {"trust": "external"}})
def open_public_pr() -> str:
    return "pull request opened"


kv.start_task()
check("read a public issue", read_public_issue, "permitted")
check("open a public pull request, no private read before it", open_public_pr, "permitted")
kv.end_task()
kv.start_task()
check("read a public issue", read_public_issue, "permitted")
check("read a private repository", read_private_repo, "permitted")
check("write to the private repository", write_private_repo, "permitted")
check("open a public pull request after the private read", open_public_pr, "refused")

# 2. A destructive action without approval (Replit).
title("2. delete-requires-approval.yaml")
kv = kernel("delete-requires-approval.yaml")


@kv.step(ActionKind.step_resource, Verb.GET)
def query() -> str:
    return "rows"


@kv.step(ActionKind.step_resource, Verb.DELETE)
def drop_table() -> str:
    return "dropped"


def approve() -> None:
    kv.add_step(
        ActionKind.step_gate,
        "human_approval",
        properties={"kind": "human"},
        output={"decision": "pass"},
    )


kv.start_task()
check("delete without an approval", drop_table, "refused")
kv.start_task()
approve()
check("query", query, "permitted")
check("delete, the approval was two steps back", drop_table, "refused")
kv.start_task()
approve()
check("delete directly after an approval", drop_table, "permitted")
kv.end_task()

# 3. A tool call scoped to an earlier result (custom rule in scoped_rule.py).
title("3. query-scoped-to-login.yaml")
kv = kernel("query-scoped-to-login.yaml")


@kv.step(ActionKind.step_credential, Verb.GET)
def authenticate() -> dict:
    return {"customer_id": 42}


@kv.step(ActionKind.step_resource, Verb.GET)
def query_customer_records(customer_id: int) -> str:
    return f"records of customer {customer_id}"


kv.start_task()
check("query customer 42 without a login", lambda: query_customer_records(customer_id=42), "refused")
kv.start_task()
authenticate()
check("query customer 42 after a login as 42", lambda: query_customer_records(customer_id=42), "permitted")
check("query customer 43 after a login as 42", lambda: query_customer_records(customer_id=43), "refused")

print()
if failures:
    print(f"{len(failures)} outcome(s) differ from what is expected: {failures}")
    sys.exit(1)
print("all outcomes as expected")
