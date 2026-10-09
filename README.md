# A coding agent under SHADI and Kyvvu

We want agents that do not do things we do not want them to do. The classic
tool for that is a [reference
monitor](https://en.wikipedia.org/wiki/Reference_monitor): a component that
sees every action before it happens and decides whether it may proceed.

[**Kyvvu**](https://kyvvu.com) is a reference monitor for agents. It runs inside
the agent's process (or as a light side-car), sees each declared step before it executes, and evaluates
it against the steps that came before it. Hence, a policy can say not just "this
tool is allowed" but "this tool is allowed only after that one". The paper
[*Runtime Governance for AI Agents: Policies on
Paths*](https://arxiv.org/abs/2603.16586) describes these path-dependent
controls; the [docs](https://docs.kyvvu.com) describe the kyvvu engine -- and various integration options -- in more detail. This demo uses a
single (local) policy, which simply says that code may only be executed after an approval
gate.

A reference monitor has to be tamper-proof, and a process cannot guarantee that
about itself. The guarantee has to come from one layer down. That layer is
[**SHADI**](https://shadi.agntcy.org) (`shadictl`, from
[AGNTCY](https://github.com/agntcy/shadi)). Before launching the agent it pins
a sandbox onto the whole process tree, saying which directories may be read or
written and whether the network is reachable, and from then on the kernel
enforces it on every syscall of every descendant (Landlock on Linux, Seatbelt
on macOS). Under SHADI the agent's code, the policy and the Kyvvu engine sit in a
read-only directory, so nothing the agent does at runtime can change what
governs it.

The demo is a small coding agent that writes Python to a scratch file and runs
it. Kyvvu decides whether the agent may take the step at all, given the steps
before it. SHADI makes sure that whatever then happens stays within the bounds
set for the process tree, and that Kyvvu itself cannot be altered.

## Quick start

```bash
./run.sh setup     # once: installs shadictl if missing, creates a venv, prepares two directories
./run.sh demo      # the four scenarios below, pausing between them
```

Requirements: `python3` (3.12 or newer), `git`, `curl`. If the installer cannot
resolve the latest SHADI release (GitHub API unreachable or rate-limited), run
`SHADI_VERSION=0.1.11 ./run.sh setup`.

## The four scenarios

The demo explores 4 scenarios (and `run.sh demo` runs them all in one go):

| | command | Kyvvu on `run_code` | result |
|---|---|---|---|
| 1 | `python agent.py tamper` | permitted (gate recorded) | generated code appends to `agent.py`; `git status` shows `M agent.py` (then restored) |
| 2 | `python agent.py tamper --no-gate` | refused: "Code execution requires a preceding gate" | nothing executes |
| 3a | `shadictl --policy sandbox.json -- python agent.py benign` | permitted | code runs, writes `agent-out/result.txt` = `42` |
| 3b | `shadictl --policy sandbox.json -- python agent.py tamper` | permitted | `PermissionError` on `agent.py`; the tree is unchanged |

Scenarios 1 and 2 show Kyvvu allowing and refusing in-process, during the execution path.

Scenario 3a simply shows an allowed, approved, sequence in which code is written and executed. Scenario 3b shows a path where again code execution is approved, so Kyvvu lets it
run. However, since the write the agent attempts is outside the sandbox, SHADI refuses it.
Both verdicts are correct. The refusal is visible on the Kyvvu side as well,
because the `step.exec` record in `agent-out/kyvvu-trace.jsonl` carries the
`PermissionError` traceback as the step's output.

Run a specific scenario using `./run.sh 1|2|3a|3b`. Do run `./run.sh clean` to remove the
generated directories.

## Verified on

| date | shadictl | kyvvu / kyvvu-engine | Python | host |
|---|---|---|---|---|
| 2026-10-09 | 0.1.11 | 0.22.1 / 0.12.0 | 3.14 | macOS, Apple Silicon (Seatbelt; `Errno 1 Operation not permitted`) |
| 2026-10-09 | 0.1.11 | 0.22.1 / 0.12.0 | 3.13 | Linux 6.18 (Landlock; `Errno 13 Permission denied`) |

`run.sh` pins `kyvvu==0.22.1`; override with `KYVVU_VERSION=...`.

## Files

| file | role |
|---|---|
| `agent.py` | the agent: `write_code` (a Kyvvu `step.resource`), `run_code` (a `step.exec`), modes `benign` / `tamper`, flag `--no-gate` |
| `demo-manifest.yaml` | the **Kyvvu policy**: `step_requires_gate` on `step.exec` |
| `sandbox.json` | the **SHADI sandbox policy** (template): read `my-agent/`, write `agent-out/` only, no network. `setup` fills in the two paths |
| `run.sh` | `setup`, `demo`, `1`, `2`, `3a`, `3b`, `clean` |
| `AGENTS.md` | the invariants the demo depends on (e.g. `shadictl` must run from `agent-out/`). Read before changing anything |

`setup` generates `my-agent/` (agent, manifest, rendered sandbox policy, venv;
read-only under SHADI, git-tracked so `git status` is the tamper check) and
`agent-out/` (the only writable directory: `scratch.py`, `result.txt`,
`kyvvu-trace.jsonl`). Neither is committed.

## Proceeding from here

A [reference monitor](https://en.wikipedia.org/wiki/Reference_monitor) mediates every relevant action, cannot be modified by the
code it governs, and is small enough to check. In this demo SHADI gives
Kyvvu the second property for everything on disk: `agent.py`, the manifest and
the Kyvvu engine sit in a directory the agent cannot write, so neither the
agent nor the code it generates can change the policy or the code that
evaluates it. Going from here to production is a matter of applying the same setup more widely.

**The trace in its own directory.** In the demo the trace is written to `agent-out/`, the directory the agent may write to, so the agent could append to its own record. Give the trace a directory of its own that the agent's sandbox policy does not list as writable. The simplest way is to run `kyvvu-engine` as a second process under its own `shadictl` launch with its own sandbox policy, reached by the agent over a unix socket; the engine then owns the trace and the agent's sandbox cannot read or write it. Two `shadictl` launches with two policies are enough for this, and the same engine process can serve several agents, including ones you did not write.

**Declaring steps at the dispatch point.** In `agent.py` each tool carries a decorator, and every call to a tool therefore passes through Kyvvu. In a real harness, declare steps at the one place all tool calls pass, the tool dispatcher, so that adding a tool never means remembering a decorator. What the generated code does inside `run_code` is the sandbox's domain, as scenario 3b shows.

**Network under the same discipline.** `sandbox.json` blocks the network entirely. A production agent needs its model API and the engine socket, and nothing else. SHADI's `net_allow` (with `shadictl --watch-policy`) limits egress to named hosts; Kyvvu's policies decide which calls to those hosts are allowed in the first place.

## License

Apache-2.0, see [LICENSE](LICENSE). SHADI is Apache-2.0 as well.
