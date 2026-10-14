"""Checks of a verify file (the verdicts of the second reviewer) and of the module overview file."""

from .store import read_json


RESOLUTIONS = ("fixed", "verifier_wrong", "sme_question")


def needs_recheck(entry):
    """True for something the resolve step wrote or corrected: no reviewer has seen that text yet."""
    return entry.get("verdict") == "added_in_resolution" or entry.get("resolution") == "fixed"


def check_verify(rules_path, verify_path):
    """Returns (errors, open_disputes, corrections_not_checked_yet)."""
    try:
        data = read_json(verify_path)
    except Exception as exc:
        return ["Verify file is not valid JSON: %s" % exc], 0, 0
    errors, disputes, unchecked = [], 0, 0

    def recheck_of(entry, name):
        if not needs_recheck(entry):
            return 0
        if entry.get("recheck") not in (None, "agree", "disagree"):
            errors.append("%s: 'recheck' must be agree or disagree." % name)
        if entry.get("recheck") == "disagree" and not str(entry.get("recheck_reason", "")).strip():
            errors.append("%s: a disagree recheck needs 'recheck_reason'." % name)
        return entry.get("recheck") is None

    rules = read_json(rules_path)
    flow = data.get("flow_verdict")
    flow = flow if isinstance(flow, dict) else {}
    groups = [("flow", "flow", [dict(flow, flow="flow")], {"flow"}),
              ("rule_id", "rule", data.get("verdicts", []), {r.get("id") for r in rules.get("rules", [])}),
              ("scenario_id", "scenario", data.get("scenario_verdicts", []),
               {s.get("id") for s in rules.get("scenarios", [])}),
              ("requirement_id", "requirement", data.get("requirement_verdicts", []),
               {q.get("id") for q in rules.get("requirements") or []})]
    for key, what, verdicts, expected in groups:
        seen = set()
        for v in verdicts:
            vid = v.get(key)
            seen.add(vid)
            allowed = ("agree", "disagree") if what == "flow" else ("agree", "disagree", "added_in_resolution")
            if v.get("verdict") not in allowed:
                errors.append("%s: verdict must be agree or disagree%s." % (
                    vid, " (add 'flow_verdict' for the flow steps)" if what == "flow" else ""))
            if v.get("verdict") == "disagree":
                if not str(v.get("reason", "")).strip():
                    errors.append("%s: a disagree verdict needs a reason." % vid)
                if v.get("resolution") not in RESOLUTIONS:
                    disputes += 1
            unchecked += recheck_of(v, vid)
        for vid in sorted(expected - seen, key=str):
            errors.append("%s: no verdict for this %s." % (vid, what))
    for n, m in enumerate(data.get("missed_rules", []), 1):
        if m.get("resolution") not in RESOLUTIONS:
            disputes += 1
        unchecked += recheck_of(m, "missed_rules entry %d" % n)
    return errors, disputes, unchecked


def check_overview(path, flow_ids):
    try:
        data = read_json(path)
    except Exception as exc:
        return ["Overview file is not valid JSON: %s" % exc]
    errors, placed = [], {}
    if not str(data.get("module_purpose", "")).strip():
        errors.append("Missing 'module_purpose'.")
    if data.get("purpose_basis") not in ("stated", "inferred"):
        errors.append("'purpose_basis' must be stated or inferred.")
    types = [t for t in data.get("flow_types") or [] if isinstance(t, dict)]
    if not types:
        errors.append("Missing 'flow_types'.")
    for t in types:
        name = str(t.get("name", "")).strip()
        if not (name and str(t.get("description", "")).strip() and t.get("flows")):
            errors.append("flow type '%s': needs name, description and flows." % name)
        for f in t.get("flows") or []:
            if f not in flow_ids:
                errors.append("flow type '%s': '%s' is not a flow in the flows index." % (name, f))
            elif f in placed:
                errors.append("%s is in two flow types: '%s' and '%s'." % (f, placed[f], name))
            placed[f] = name
    for f in sorted(flow_ids - set(placed)):
        errors.append("%s is not in any flow type." % f)
    return errors
