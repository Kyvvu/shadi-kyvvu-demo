"""A custom Kyvvu rule: an input field of a step must equal an output field of an earlier step.

kyvvu-engine has no built-in rule that compares an argument of one step with
the output of another. A rule function is ordinary Python, registered with
``PolicyRule.register``. Import this module before the Kyvvu policy that names
``input_equals_history_output`` is loaded.

Used by ``query-scoped-to-login.yaml``: ``query_customer_records`` may only be
called with the ``customer_id`` that ``authenticate`` returned earlier in the
same task.
"""

from kyvvu_engine.rules import PolicyRule


def _get(obj, path):
    """Follow a dotted path through nested dictionaries; None when it is missing."""
    for key in path.split("."):
        if not isinstance(obj, dict) or key not in obj:
            return None
        obj = obj[key]
    return obj


@PolicyRule.register(
    name="input_equals_history_output",
    description=(
        "An input field of the step must equal an output field of the latest "
        "earlier step with the given step_name."
    ),
    params_schema={
        "source_step_name": {
            "type": "string",
            "required": True,
            "description": "step_name of the step that produced the value",
        },
        "source_output_field": {
            "type": "string",
            "required": True,
            "description": "Path inside that step's output",
        },
        "target_input_field": {
            "type": "string",
            "required": True,
            "description": "Path inside the current step's input",
        },
        "target_step_names": {
            "type": "array",
            "required": True,
            "description": "step_names this applies to",
        },
    },
    enforcement_points=["step_execution"],
)
def input_equals_history_output(data, params, context) -> bool:
    if data.step_name not in params["target_step_names"]:
        return True
    source = next(
        (
            step
            for step in reversed(context.get_all_steps_in_task())
            if step.step_name == params["source_step_name"]
            and isinstance(step.output, dict)
        ),
        None,
    )
    bound = _get(source.output, params["source_output_field"]) if source else None
    actual = _get(data.input or {}, params["target_input_field"])
    return bound is not None and actual == bound
