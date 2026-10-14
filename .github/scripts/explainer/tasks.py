"""The task line each AI agent is given: which instruction file to read, and for what."""

import os

from .state import documented
from .store import HERE, out_dir, shown, write_json

# state of a work item -> (instruction file of the next step, advice for a person who runs the step by hand)
STEP = {
    "TODO": ("extract.md", "Use Claude Sonnet (Opus for a large or confusing flow)."),
    "EXTRACT_INVALID": ("extract.md", "The rules file has problems. Run the step again."),
    "EXTRACTED": ("verify.md", "Use a different model from the extract step, in a NEW chat."),
    "VERIFY_INVALID": ("verify.md", "The verify file has problems. Run the step again in a NEW chat."),
    "DISPUTED": ("resolve.md", "Use Claude Opus, in a NEW chat."),
    "RECHECK": ("recheck.md", "Use a different model from the resolve step, in a NEW chat."),
}


def step_file(state):
    return STEP[state][0]


def step_name(state):
    """'extract', 'verify', 'resolve' or 'recheck': also the last part of the agent name."""
    return step_file(state)[:-3]


def item_task(module, item_id, state):
    return "Read %s and follow it. Work item: %s" % (shown(os.path.join(HERE, "steps", step_file(state))),
                                                    shown(out_dir(module, "work", item_id + ".json")))


def overview_task(module):
    """Writes the flows index (all the overview step may read) and returns the task line."""
    index = []
    for w, rules in documented(module):
        index.append({
            "id": w["id"], "kind": w["kind"], "entry_points": [e["method"] for e in w["entry_points"]],
            "title": rules["flow_title"], "summary": rules["flow_summary"], "purpose": rules["flow_purpose"],
            "starts_when": rules["starts_when"],
            "ends": [s["text"] for s in rules["flow_steps"] if s["kind"] == "end"],
        })
    index_path = out_dir(module, "flows-index.json")
    write_json(index_path, index)
    return "Read %s and follow it. Module: %s. Flows index: %s. Output file: %s" % (
        shown(os.path.join(HERE, "steps", "overview.md")), module, shown(index_path),
        shown(out_dir(module, "overview.json")))


def notes_hint(module):
    """Sends the agent to the module notes first. Empty when the module has none."""
    path = out_dir(module, "module-info.md")
    if not os.path.isfile(path):
        return ""
    return " First read %s: the business domain of this module and what the business team says about " \
           "it. Use it for names and meaning; if the code does something different, the code wins and " \
           "you add a question for the SME." % shown(path)
