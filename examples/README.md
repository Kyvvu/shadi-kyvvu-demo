# Further Kyvvu policies

The demo itself has one Kyvvu policy. This directory has three more, each for a
case where the order of the agent's steps matters. They are discussed in the
[blog post](https://blogs.agntcy.org) on running a reference monitor inside SHADI.

```bash
./run.sh setup      # once, from the repository root
./run.sh examples   # runs the three policies and checks each outcome
```

| file | rule | case |
|---|---|---|
| `no-external-write-after-confidential-read.yaml` | a write to an external target is refused after a read of confidential data | individually allowed steps that leak together ([GitHub MCP, Invariant Labs](https://invariantlabs.ai/blog/mcp-github-vulnerability)) |
| `delete-requires-approval.yaml` | a delete needs a human approval directly before it | a destructive action without approval ([Replit](https://www.theregister.com/2025/07/22/replit_saastr_response/)) |
| `query-scoped-to-login.yaml` | a query may only use the customer id the login returned | a tool call scoped to an earlier result |
| `scoped_rule.py` | the rule function `input_equals_history_output` that the third policy names | |
| `run_examples.py` | declares a few steps per policy and compares what Kyvvu permitted and refused with what is expected | |

The tools in `run_examples.py` do nothing: only the declared steps, their
properties and their order matter. The examples need no SHADI, no network and
no Kyvvu account.

A rule only works if the harness declares the steps involved, with the
properties the rule names. The first policy, for example, requires that a read
of a private repository is declared with `data.classification: confidential`
and a public repository with `target.trust: external`.
