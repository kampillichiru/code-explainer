"""Checks of a rules file: what the extract agent wrote for one work item.

check_rules returns a list of messages for the agent. An empty list means the file passes.
The flow and its scenarios are checked in flow_check.py, the code runs in run_check.py.
"""

import os
import re

from . import java_index, run_check
from .flow_check import check_flow
from .store import file_hash, load_config, out_dir, read_json, under

RULE_TEXT_FIELDS = ["title", "what_it_does", "business_reason", "how_it_is_calculated"]
FLOW_TEXT_FIELDS = ["flow_title", "flow_summary", "flow_purpose", "starts_when"]
REASON_BASIS = {"stated": "", "inferred": " *(worked out from the code - to be confirmed by the SME)*",
                "unknown": " *(not known from the code - see questions)*"}
VALUE_SOURCES = {"input": "Given as input", "database": "Read from the database", "fixed": "Fixed in the code",
                 "calculated": "Calculated", "config": "Set in a configuration file", "other_module": "From another module", "system": "From the system"}
WORD_LIMITS = {"flow_summary": 60, "flow_purpose": 40, "starts_when": 40}
RULE_WORD_LIMITS = {"title": 10, "what_it_does": 40, "business_reason": 35, "how_it_is_calculated": 45}
SCENARIO_WORD_LIMITS = {"title": 10, "outcome": 30, "user_sees": 30}
MAX_SCENARIOS, MAX_EXAMPLE_STEPS, MAX_QUESTIONS, MAX_CONDITIONS = 10, 6, 3, 6
REQUIREMENT_WORDS, STEP_WORDS, QUESTION_WORDS, CONDITION_WORDS = 45, 12, 35, 25
NUMBER_RE = re.compile(r"(?<![\w.])\d[\d,]*(?:\.\d+)?")


def check_rules(work, rules_path):
    """Returns a list of error messages. An empty list means the rules file passes."""
    errors = []
    try:
        data = read_json(rules_path)
    except Exception as exc:
        return ["Rules file is not valid JSON: %s" % exc]
    root = load_config()["source_root"]
    allowed = {m["file"] for m in work["methods_to_document"] + work["context_methods"]}
    items = {i["id"]: i for i in work["items_to_cover"]}
    for field in FLOW_TEXT_FIELDS:
        if not str(data.get(field, "")).strip():
            errors.append("Missing '%s'." % field)
    if not data.get("inputs"):
        errors.append("Missing 'inputs': list what the flow is given when it starts.")

    handled, ids = {}, set()  # checklist item -> the rules that cover it; the rule ids of this file
    for n, r in enumerate(data.get("rules", []), 1):
        rid = r.get("id", "(rule %d)" % n)
        if not re.fullmatch(re.escape(work["id"]) + r"-R\d+", str(rid)):
            errors.append("%s: id must look like %s-R1." % (rid, work["id"]))
        if rid in ids:
            errors.append("%s: id is used twice." % rid)
        ids.add(rid)
        errors += check_rule_content(rid, r)
        sources = r.get("sources") or []
        if not sources:
            errors.append("%s: no 'sources'. Every rule needs file and lines." % rid)
        errors += check_exact_values(rid, r.get("values_used") or [], sources, root)
        errors += check_sources(rid, sources, allowed, root)
        errors += check_covers(rid, r, sources, items, handled)
    errors += check_checklist(data, items, handled)
    for g in data.get("glossary", []):
        if not (g.get("technical_name") and g.get("business_meaning")):
            errors.append("glossary: each entry needs technical_name and business_meaning.")
    return errors + check_surroundings(data) + check_flow(data, work["id"], ids) \
        + check_requirements(data, work["id"], ids) + check_sizes(data) + check_runs(work, data, ids)


def check_rule_content(rid, r):
    """One rule says what it does, when, why, with which values, and shows an example."""
    errors = []
    for field in RULE_TEXT_FIELDS:
        if not str(r.get(field, "")).strip():
            errors.append("%s: '%s' is empty." % (rid, field))
    if not r.get("when_it_applies"):
        errors.append("%s: 'when_it_applies' is empty." % rid)
    ex = r.get("example") or {}
    if not (ex.get("inputs") and ex.get("steps") and str(ex.get("result", "")).strip()):
        errors.append("%s: 'example' needs inputs, steps and result." % rid)
    if r.get("status") not in ("clear", "unclear"):
        errors.append("%s: 'status' must be clear or unclear." % rid)
    if r.get("status") == "unclear" and not r.get("questions_for_sme"):
        errors.append("%s: status is unclear, so 'questions_for_sme' is needed." % rid)
    if r.get("reason_basis") not in REASON_BASIS:
        errors.append("%s: 'reason_basis' must be stated, inferred or unknown." % rid)
    if r.get("reason_basis") == "unknown" and not r.get("questions_for_sme"):
        errors.append("%s: the business reason is unknown, so ask the SME in 'questions_for_sme'." % rid)
    values = r.get("values_used") or []
    if not values:
        errors.append("%s: 'values_used' is empty. List each value the rule uses or produces." % rid)
    for v in values:
        if not (isinstance(v, dict) and str(v.get("name", "")).strip() and str(v.get("value", "")).strip()):
            errors.append("%s: each entry of 'values_used' needs name and value." % rid)
        elif v.get("comes_from") not in VALUE_SOURCES:
            errors.append("%s: value '%s': 'comes_from' must be one of %s."
                          % (rid, v["name"], ", ".join(VALUE_SOURCES)))
    return errors


def check_sources(rid, sources, allowed, root):
    """The file and lines a rule points to exist and belong to the work item."""
    errors = []
    for s in sources:
        f, a, b = s.get("file"), s.get("start_line"), s.get("end_line")
        path = under(root, str(f))
        if f not in allowed:
            errors.append("%s: source file '%s' is not part of this work item." % (rid, f))
        elif not os.path.isfile(path):
            errors.append("%s: source file '%s' does not exist." % (rid, f))
        else:
            count = len(java_index.read_text(path).splitlines())
            if not (isinstance(a, int) and isinstance(b, int) and 1 <= a <= b <= count):
                errors.append("%s: lines %s-%s are not inside %s (%d lines)." % (rid, a, b, f, count))
    return errors


def check_covers(rid, r, sources, items, handled):
    """What a rule says it covers is on the checklist, inside the lines the rule points to. Fills 'handled'."""
    errors = []
    for c in r.get("covers") or []:
        if c not in items:
            errors.append("%s: covers '%s', which is not in items_to_cover." % (rid, c))
            continue
        handled.setdefault(c, []).append(rid)
        it = items[c]
        inside = any(s.get("file") == it["file"] and isinstance(s.get("start_line"), int)
                     and isinstance(s.get("end_line"), int)
                     and s["start_line"] <= it["line"] <= s["end_line"] for s in sources)
        if not inside:
            errors.append("%s: covers %s but no source range contains line %d." % (rid, c, it["line"]))
    return errors


def check_checklist(data, items, handled):
    """Every item of the checklist is covered by a rule, or marked 'no business rule' with a reason."""
    errors = []
    for e in data.get("no_business_rule", []):
        c = e.get("item")
        if c not in items:
            errors.append("no_business_rule: '%s' is not in items_to_cover." % c)
        elif c in handled:
            errors.append("%s is covered by a rule and also marked no_business_rule." % c)
        elif not str(e.get("reason", "")).strip():
            errors.append("no_business_rule: '%s' has no reason." % c)
        else:
            handled[c] = ["none"]
    for c in items:
        if c not in handled:
            errors.append("Not handled: %s   -> %s" % (c, items[c]["text"]))
    return errors


def check_runs(work, data, rule_ids):
    """Runs the code with the inputs given in 'code_runs' and compares what it returns with what the file says."""
    cfg = load_config()
    files = sorted({m["file"] for m in work["methods_to_document"] + work["context_methods"]})
    hashes = {f: file_hash(under(cfg["source_root"], f)) for f in files if os.path.isfile(under(cfg["source_root"], f))}
    return run_check.check(work, data, rule_ids, cfg, cfg["source_root"], out_dir(work["module"], "exec"), hashes)


def numbers_in(text):
    """The numbers in a text as plain values: '86,400,000' and '2.50' become 86400000 and 2.5."""
    found = set()
    for raw in NUMBER_RE.findall(str(text)):
        parts = raw.rstrip(",").split(",")
        thousands = len(parts) > 1 and all(len(p.split(".")[0]) == 3 for p in parts[1:])
        for token in ([raw.replace(",", "")] if thousands else parts):
            try:
                found.add(float(token))
            except ValueError:
                pass
    return found


def check_exact_values(rid, values, sources, root):
    """A value marked as fixed in the code, or set in a configuration file, must be in the lines the rule points to."""
    cited = []
    for s in sources:
        path = under(root, str(s.get("file")))
        a, b = s.get("start_line"), s.get("end_line")
        if os.path.isfile(path) and isinstance(a, int) and isinstance(b, int):
            cited += java_index.read_text(path).splitlines()[a - 1:b]
    in_code = numbers_in("\n".join(cited))
    for word, n in (("ZERO", 0.0), ("ONE", 1.0), ("TEN", 10.0)):  # BigDecimal.ZERO and the like
        if re.search(r"\b%s\b" % word, "\n".join(cited)):
            in_code.add(n)
    errors = []
    for v in values:
        if not isinstance(v, dict) or v.get("comes_from") not in ("fixed", "config"):
            continue
        text = str(v.get("value", ""))
        for n in sorted(numbers_in(text)):
            percent = re.search(r"(?<![\w.])%s\s*%%" % re.escape("%g" % n), text)
            if n not in in_code and not (percent and round(n / 100, 10) in in_code):
                errors.append("%s: value '%s' has the number %g, which is not in the code lines of 'sources'. Write the "
                              "value exactly as it is in the code, or add the lines where it is set to 'sources'."
                              % (rid, v.get("name"), n))
    return errors


def check_sizes(data):
    """A document nobody reads to the end is not reliable either: every kind of statement has a size limit."""
    errors = []

    def words(name, text, limit):
        n = len(str(text or "").split())
        if n > limit:
            errors.append("%s has %d words. The limit is %d. Say it shorter." % (name, n, limit))

    def count(name, entries, limit, what):
        if len(entries or []) > limit:
            errors.append("%s has %d %s. The limit is %d. Keep the ones that matter." % (name, len(entries), what, limit))

    for field, limit in WORD_LIMITS.items():
        words("'%s'" % field, data.get(field), limit)
    count("'flow_questions_for_sme'", data.get("flow_questions_for_sme"), MAX_QUESTIONS, "questions")
    for q in data.get("flow_questions_for_sme") or []:
        words("A question in 'flow_questions_for_sme'", q, QUESTION_WORDS)
    for s in data.get("flow_steps") or []:
        if isinstance(s, dict):
            words("flow_steps %s: 'text'" % s.get("id"), s.get("text"), STEP_WORDS)
    for q in data.get("requirements") or []:
        if isinstance(q, dict):
            words("%s: 'text'" % q.get("id"), q.get("text"), REQUIREMENT_WORDS)
    for r in data.get("rules") or []:
        rid = r.get("id")
        for field, limit in RULE_WORD_LIMITS.items():
            words("%s: '%s'" % (rid, field), r.get(field), limit)
        count("%s: 'when_it_applies'" % rid, r.get("when_it_applies"), MAX_CONDITIONS, "conditions")
        for c in r.get("when_it_applies") or []:
            words("%s: a condition in 'when_it_applies'" % rid, c, CONDITION_WORDS)
        count("%s: the example" % rid, (r.get("example") or {}).get("steps"), MAX_EXAMPLE_STEPS, "steps")
        count("%s: 'questions_for_sme'" % rid, r.get("questions_for_sme"), MAX_QUESTIONS, "questions")
        for q in r.get("questions_for_sme") or []:
            words("%s: a question" % rid, q, QUESTION_WORDS)
    scenarios = [s for s in data.get("scenarios") or [] if isinstance(s, dict)]
    count("'scenarios'", scenarios, MAX_SCENARIOS, "scenarios")
    for sc in scenarios:
        for field, limit in SCENARIO_WORD_LIMITS.items():
            words("%s: '%s'" % (sc.get("id"), field), sc.get(field), limit)
        count("%s: the example" % sc.get("id"), (sc.get("example") or {}).get("steps"), MAX_EXAMPLE_STEPS, "steps")
    if not data.get("rules"):  # code with no business behaviour gets the short form
        if len(data.get("flow_steps") or []) > 3 or len(scenarios) > 1:
            errors.append("This file has no rules, so the code has no business behaviour. Use the short form: "
                          "at most 3 flow steps (start, one step, end) and 1 scenario.")
    return errors


def check_requirements(data, work_id, rule_ids):
    """Checks the 'The system shall ...' statements and their links to the rules."""
    errors, seen, linked = [], set(), set()
    reqs = [q for q in data.get("requirements") or [] if isinstance(q, dict)]
    if rule_ids and not reqs:
        return ["Missing 'requirements': one 'The system shall ...' statement for each behaviour."]
    for n, q in enumerate(reqs, 1):
        qid = q.get("id", "(requirement %d)" % n)
        if not re.fullmatch(re.escape(work_id) + r"-FR\d+", str(qid)):
            errors.append("%s: requirement id must look like %s-FR1." % (qid, work_id))
        if qid in seen:
            errors.append("%s: requirement id is used twice." % qid)
        seen.add(qid)
        shalls = len(re.findall(r"\bshall\b", str(q.get("text", ""))))
        if shalls != 1:
            errors.append("%s: 'text' must be one 'shall' statement (it has %d). One behaviour in one requirement; "
                          "split it if it says two things." % (qid, shalls))
        if not q.get("rules"):
            errors.append("%s: 'rules' is empty. Link the requirement to the rules it rests on." % qid)
        for rid in q.get("rules") or []:
            if rid not in rule_ids:
                errors.append("%s: rule '%s' is not in this file." % (qid, rid))
            linked.add(rid)
    for rid in sorted(rule_ids - linked, key=str):
        errors.append("%s: no requirement rests on this rule. Add it to the 'rules' of a requirement." % rid)
    return errors


def check_surroundings(data):
    """Checks who uses the flow, what must be true before it runs, and what comes out."""
    errors = []
    for field, hint in (("preconditions", 'Write "None found in the code" if there is none.'),
                        ("outputs", "List what comes out, in business names.")):
        if not data.get(field):
            errors.append("Missing '%s'. %s" % (field, hint))
    roles = data.get("users_and_roles") or []
    if not roles or not all(isinstance(u, dict) and str(u.get("role", "")).strip()
                            and str(u.get("allowed_to", "")).strip() for u in roles):
        errors.append("'users_and_roles': each entry needs 'role' and 'allowed_to'. If the code does not show "
                      "who uses the flow, write one entry with the role \"Not known from the code\".")
    if data.get("roles_basis") not in REASON_BASIS:
        errors.append("'roles_basis' must be stated, inferred or unknown.")
    return errors
