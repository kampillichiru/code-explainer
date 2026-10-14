"""The state of a work item and of the module overview.

There is no database: the state follows from which files exist and whether they pass the checks."""

import os

from .rules_check import check_rules
from .store import HERE, out_dir, read_json, work_items
from .verify_check import check_overview, check_verify


def item_state(work):
    rules_path = os.path.join(HERE, "output", work["module"], "rules", work["id"] + ".json")
    verify_path = os.path.join(HERE, "output", work["module"], "verify", work["id"] + ".json")
    if not os.path.isfile(rules_path):
        return "TODO", []
    errors = check_rules(work, rules_path)
    if errors:
        return "EXTRACT_INVALID", errors
    if not os.path.isfile(verify_path):
        return "EXTRACTED", []
    errors, disputes, unchecked = check_verify(rules_path, verify_path)
    if errors:
        return "VERIFY_INVALID", errors
    return ("DISPUTED" if disputes else "RECHECK" if unchecked else "DONE"), []


def gather(module):
    rows = []
    for w in work_items(module):
        state, _ = item_state(w)
        rules = verify = None
        if state != "TODO":
            rules = read_json(out_dir(module, "rules", w["id"] + ".json"))
        vpath = out_dir(module, "verify", w["id"] + ".json")
        if state in ("DISPUTED", "RECHECK", "DONE"):
            verify = read_json(vpath)
        rows.append((w, state, rules, verify))
    return rows


def documented(module):
    """Work items whose rules file passes validation, with their rules."""
    return [(w, rules) for w, state, rules, _v in gather(module) if state not in ("TODO", "EXTRACT_INVALID")]


def overview_state(module):
    """NONE (no flow documented yet), OVERVIEW_TODO, OVERVIEW_INVALID or DONE, with the errors."""
    flows = documented(module)
    path = out_dir(module, "overview.json")
    if not flows:
        return "NONE", []
    if not os.path.isfile(path):
        return "OVERVIEW_TODO", []
    errors = check_overview(path, {w["id"] for w, _r in flows})
    return ("OVERVIEW_INVALID" if errors else "DONE"), errors
