"""Checks of the flow in a rules file: the steps of the diagram, and the scenarios that walk through them."""

import re

MAX_FLOW_STEPS = 25  # more boxes than this and the diagram is no longer easy to read
SCENARIO_TYPES = ("main", "alternate", "exception")


def check_flow(data, work_id, rule_ids):
    """Returns the error messages for 'flow_steps' and 'scenarios'."""
    steps = [s for s in data.get("flow_steps") or [] if isinstance(s, dict)]
    if not steps:
        return ["Missing 'flow_steps': describe the flow from the entry point to every end."]
    errors, by_id, edges = check_steps(steps, rule_ids)
    return errors + check_scenarios(data, work_id, by_id, edges)


def check_steps(steps, rule_ids):
    """Returns (errors, steps by id, arrows). An arrow is {(from, to): label}; the label is '' outside a decision."""
    errors = []
    by_id, edges, incoming, linked = {}, {}, set(), set()
    for s in steps:
        sid = str(s.get("id"))
        if not re.fullmatch(r"[A-Z]\d+", sid):
            errors.append("flow_steps: id '%s' must be one capital letter and a number, like S1." % sid)
        if sid in by_id:
            errors.append("flow_steps: id '%s' is used twice." % sid)
        by_id[sid] = s
    for s in steps:
        sid, kind = str(s.get("id")), s.get("kind")
        if not str(s.get("text", "")).strip():
            errors.append("flow_steps %s: 'text' is empty." % sid)
        if kind in ("start", "step"):
            targets = [("", s.get("next"))]
        elif kind == "decision":
            branches = [b for b in s.get("branches") or [] if isinstance(b, dict)]
            if len(branches) < 2 or not all(str(b.get("label", "")).strip() for b in branches):
                errors.append("flow_steps %s: a decision needs two or more 'branches', each with label and to." % sid)
            targets = [(b.get("label"), b.get("to")) for b in branches]
        elif kind == "end":
            targets = []
        else:
            errors.append("flow_steps %s: 'kind' must be start, step, decision or end." % sid)
            continue
        for label, to in targets:
            if to not in by_id:
                errors.append("flow_steps %s: points to '%s', which is not a step id." % (sid, to))
            else:
                edges[(sid, to)] = label
                incoming.add(to)
        for rid in s.get("rules") or []:
            if rid not in rule_ids:
                errors.append("flow_steps %s: rule '%s' is not in this file." % (sid, rid))
            linked.add(rid)
        if kind == "decision" and rule_ids and not s.get("rules"):
            errors.append("flow_steps %s: a decision needs the rule that describes it in 'rules'." % sid)

    kinds = [s.get("kind") for s in steps]
    if "start" not in kinds or "end" not in kinds:
        errors.append("flow_steps: needs at least one 'start' step and one 'end' step.")
    if len(steps) > MAX_FLOW_STEPS:
        errors.append("flow_steps: %d steps. Keep the diagram simple: at most %d. Put one business step "
                      "in one box and leave the detail to the rules." % (len(steps), MAX_FLOW_STEPS))
    for sid, s in by_id.items():
        if s.get("kind") != "start" and sid not in incoming:
            errors.append("flow_steps %s: no step leads to it." % sid)
    for rid in sorted(rule_ids - linked, key=str):
        errors.append("%s: not linked to any flow step. Add it to the 'rules' of the step it belongs to." % rid)
    return errors, by_id, edges


def check_scenarios(data, work_id, by_id, edges):
    """Every scenario is a real way from a start to an end, and together they follow every arrow."""
    errors = []
    scenarios = [s for s in data.get("scenarios") or [] if isinstance(s, dict)]
    if not scenarios:
        errors.append("Missing 'scenarios': list each way through the flow, from start to end.")
    walked, seen = set(), set()
    for n, sc in enumerate(scenarios, 1):
        cid = sc.get("id", "(scenario %d)" % n)
        if not re.fullmatch(re.escape(work_id) + r"-SC\d+", str(cid)):
            errors.append("%s: scenario id must look like %s-SC1." % (cid, work_id))
        if cid in seen:
            errors.append("%s: scenario id is used twice." % cid)
        seen.add(cid)
        errors += check_scenario_texts(cid, sc)
        path = sc.get("path") or []
        unknown = [p for p in path if p not in by_id]
        if unknown or len(path) < 2:
            errors.append("%s: 'path' must list step ids from a start to an end. Not valid: %s" % (cid, unknown or path))
            continue
        if by_id[path[0]].get("kind") != "start" or by_id[path[-1]].get("kind") != "end":
            errors.append("%s: 'path' must begin at a start step and stop at an end step." % cid)
        for a, b in zip(path, path[1:]):
            if (a, b) in edges:
                walked.add((a, b))
            else:
                errors.append("%s: 'path' goes from %s to %s, but the flow has no arrow there." % (cid, a, b))
    if scenarios and not any(sc.get("type") == "main" for sc in scenarios):
        errors.append("No scenario has the type 'main'. Mark the normal case as main.")
    if scenarios:
        for (a, b), label in edges.items():
            if (a, b) not in walked:
                errors.append("No scenario follows the arrow %s -> %s%s. Add a scenario for this case."
                              % (a, b, " (%s)" % label if label else ""))
    return errors


def check_scenario_texts(cid, sc):
    errors = []
    for field in ("title", "outcome"):
        if not str(sc.get(field, "")).strip():
            errors.append("%s: '%s' is empty." % (cid, field))
    if not sc.get("when"):
        errors.append("%s: 'when' is empty. List the conditions of this scenario." % cid)
    if sc.get("type") not in SCENARIO_TYPES:
        errors.append("%s: 'type' must be main, alternate or exception." % cid)
    elif sc["type"] != "main" and not str(sc.get("user_sees", "")).strip():
        errors.append("%s: 'user_sees' is empty. Say what the user or the calling system gets back." % cid)
    ex = sc.get("example") or {}
    if not (ex.get("inputs") and ex.get("steps") and str(ex.get("result", "")).strip()):
        errors.append("%s: 'example' needs inputs, steps and result." % cid)
    return errors
