"""Code Explainer - turns source code into a business logic document. Command line tool.

  python explain.py selfcheck
  python explain.py run MODULE [--path FOLDER] [--about "TEXT" | --about-file FILE] [--parallel N]
  python explain.py prepare MODULE [--path FOLDER] [--about "TEXT" | --about-file FILE]
  python explain.py step MODULE
  python explain.py inventory MODULE [--force]
  python explain.py next MODULE
  python explain.py validate ITEM_ID
  python explain.py validate-overview MODULE
  python explain.py status MODULE
  python explain.py coverage MODULE
  python explain.py build-doc MODULE
"""
import hashlib
import json
import os
import re
import sys
import time

def long_path(path):
    """Windows refuses paths over 260 characters unless they carry this prefix."""
    path = os.path.abspath(path)
    if os.name == "nt" and not path.startswith("\\\\"):
        path = "\\\\?\\" + path
    return path


def plain(path):
    return path[4:] if path.startswith("\\\\?\\") else path


def under(root, rel):
    """Joins a path from config or JSON (which uses /) to a root folder."""
    return os.path.join(root, os.path.normpath(rel))


def json_files(folder):
    if not os.path.isdir(folder):
        return []
    return [os.path.join(folder, n) for n in sorted(os.listdir(folder)) if n.endswith(".json")]


SCRIPTS = os.path.dirname(os.path.abspath(__file__))
HERE = long_path(os.path.dirname(SCRIPTS))  # the package folder: config.json, steps, output
ITEM_KINDS = ["if", "case", "ternary", "catch", "sql", "method", "config"]
RULE_TEXT_FIELDS = ["title", "what_it_does", "business_reason", "how_it_is_calculated"]
FLOW_TEXT_FIELDS = ["flow_title", "flow_summary", "flow_purpose", "starts_when"]
REASON_BASIS = {"stated": "", "inferred": " *(worked out from the code - to be confirmed by the SME)*",
                "unknown": " *(not known from the code - see questions)*"}
VALUE_SOURCES = {"input": "Given as input", "database": "Read from the database", "fixed": "Fixed in the code",
                 "calculated": "Calculated", "config": "Set in a configuration file", "other_module": "From another module", "system": "From the system"}
MAX_FLOW_STEPS = 25  # more boxes than this and the diagram is no longer easy to read
RESOLUTIONS = ("fixed", "verifier_wrong", "sme_question")
SCENARIO_TYPES = ("main", "alternate", "exception")


# ---------------------------------------------------------------- helpers

def load_config():
    cfg = json.load(open(os.path.join(HERE, "config.json"), encoding="utf-8"))
    cfg["source_root"] = long_path(os.path.join(plain(HERE), cfg["source_root"]))
    return cfg


def out_dir(module, *parts):
    return os.path.join(HERE, "output", module, *parts)


def read_json(path):
    with open(path, encoding="utf-8-sig") as fh:
        return json.load(fh)


def write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)


def shown(path):
    """Path as the Copilot agent should see it: relative to the project root when possible."""
    root = load_config()["source_root"]
    rel = os.path.relpath(path, root)
    return (plain(path) if rel.startswith("..") else rel).replace("\\", "/")


def module_dirs(cfg, module):
    """A module is one folder or a list of folders (Java, SQL scripts, configuration)."""
    rels = cfg["modules"][module]
    return [under(cfg["source_root"], r) for r in ([rels] if isinstance(rels, str) else rels)]


def work_items(module):
    return [read_json(p) for p in json_files(out_dir(module, "work"))]


def module_of(item_id):
    return item_id.rsplit("-", 1)[0]


# ---------------------------------------------------------------- inventory

def cmd_inventory(module, force=False):
    import java_index
    cfg = load_config()
    if module not in cfg["modules"]:
        sys.exit("Module '%s' is not listed in config.json" % module)
    if json_files(out_dir(module, "rules")) and not force:
        sys.exit("Rules already exist for %s. Running inventory again renumbers the work items.\n"
                 "Use --force only if you want to start this module again." % module)
    dirs = module_dirs(cfg, module)
    for d in dirs:
        if not os.path.isdir(d):
            sys.exit("Folder not found: %s" % d)
    kinds = cfg.get("item_kinds", ITEM_KINDS)
    index = java_index.resolve_calls(java_index.index_module(cfg["source_root"], dirs, kinds, cfg.get("file_types")))
    methods = index["methods"]

    callers = {mid: set() for mid in methods}
    for mid, m in methods.items():
        for c in m["callees"]:
            callers[c].add(mid)

    def reach(start):
        seen, order, todo = set(), [], [start]
        while todo:
            mid = todo.pop()
            if mid in seen:
                continue
            seen.add(mid)
            order.append(mid)
            todo.extend(reversed(methods[mid]["callees"]))
        return order

    # Java first: a stored procedure that Java calls then belongs to the Java flow that calls it
    ordered = sorted(methods.values(), key=lambda m: (not m["file"].endswith(".java"), m["file"], m["start"]))
    entries = [m["id"] for m in ordered if not callers[m["id"]] and not m["private"]]
    owner, units = {}, []
    for entry in entries:
        owned = [mid for mid in reach(entry) if mid not in owner]
        for mid in owned:
            owner[mid] = entry
        owned = [mid for mid in owned if methods[mid]["items"]]
        if owned:
            units.append({"entries": [entry], "methods": owned, "kind": "flow"})
    # code that no entry point reaches (private and never called, or call cycles)
    for m in ordered:
        if m["id"] not in owner and m["items"]:
            units.append({"entries": [m["id"]], "methods": [m["id"]], "kind": "unreached"})

    units.sort(key=lambda u: not methods[u["entries"][0]]["file"].endswith(".java"))  # stable: Java keeps its numbers

    def size(mids):
        return sum(methods[x]["end"] - methods[x]["start"] + 1 for x in mids)

    target, limit = cfg.get("target_lines", 400), cfg.get("max_lines", 1200)
    groups = []
    for u in units:
        last = groups[-1] if groups else None
        same_file = last and methods[last["entries"][0]]["file"] == methods[u["entries"][0]]["file"]
        if same_file and last["kind"] == u["kind"] and size(last["methods"] + u["methods"]) <= target:
            last["entries"] += u["entries"]
            last["methods"] += u["methods"]
        else:
            groups.append(u)
    parts = []
    for g in groups:
        chunk = []
        for mid in g["methods"]:
            if chunk and size(chunk + [mid]) > limit:
                parts.append(dict(g, methods=chunk))
                chunk = []
            chunk.append(mid)
        parts.append(dict(g, methods=chunk))

    for old in json_files(out_dir(module, "work")):
        os.remove(old)

    def brief(mid):
        m = methods[mid]
        return {"method": mid.split("#", 1)[1].rsplit(":", 1)[0], "file": m["file"],
                "start_line": m["start"], "end_line": m["end"]}

    total_items = 0
    for n, p in enumerate(parts, 1):
        item_id = "%s-%03d" % (module, n)
        own = set(p["methods"])
        context, external = [], set()
        for mid in p["methods"]:
            external.update(methods[mid]["external"])
            for c in methods[mid]["callees"] + methods[mid]["reads"]:
                if c not in own and c not in context and not methods[c]["trivial"]:
                    context.append(c)
        items = [i for mid in p["methods"] for i in methods[mid]["items"]]
        total_items += len(items)
        write_json(out_dir(module, "work", item_id + ".json"), {
            "id": item_id, "module": module, "kind": p["kind"],
            "source_root": plain(cfg["source_root"]).replace("\\", "/"),
            "entry_points": [brief(e) for e in p["entries"]],
            "methods_to_document": [brief(mid) for mid in p["methods"]],
            "context_methods": [brief(c) for c in context],
            "calls_to_other_modules": sorted(external),
            "items_to_cover": items,
            "rules_file": shown(out_dir(module, "rules", item_id + ".json")),
            "verify_file": shown(out_dir(module, "verify", item_id + ".json")),
        })
    failed = {f: v["error"] for f, v in index["files"].items() if not v["parsed"]}
    write_json(out_dir(module, "inventory.json"), {
        "module": module, "files": len(index["files"]), "methods": len(methods),
        "trivial_methods": sum(1 for m in methods.values() if m["trivial"]),
        "work_items": len(parts), "items_to_cover": total_items,
        "files_not_parsed": failed,
    })
    print("Module %s: %d files, %d methods, %d work items, %d items to cover."
          % (module, len(index["files"]), len(methods), len(parts), total_items))
    if failed:
        print("%d file(s) could not be parsed. Each is one work item for the whole file:" % len(failed))
        for f, err in failed.items():
            print("  %s  (%s)" % (f, err))


# ---------------------------------------------------------------- validate

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
    handled, ids = {}, set()
    for n, r in enumerate(data.get("rules", []), 1):
        rid = r.get("id", "(rule %d)" % n)
        if not re.fullmatch(re.escape(work["id"]) + r"-R\d+", str(rid)):
            errors.append("%s: id must look like %s-R1." % (rid, work["id"]))
        if rid in ids:
            errors.append("%s: id is used twice." % rid)
        ids.add(rid)
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
        sources = r.get("sources") or []
        if not sources:
            errors.append("%s: no 'sources'. Every rule needs file and lines." % rid)
        errors += check_exact_values(rid, values, sources, root)
        for s in sources:
            f, a, b = s.get("file"), s.get("start_line"), s.get("end_line")
            path = under(root, str(f))
            if f not in allowed:
                errors.append("%s: source file '%s' is not part of this work item." % (rid, f))
            elif not os.path.isfile(path):
                errors.append("%s: source file '%s' does not exist." % (rid, f))
            else:
                import java_index
                count = len(java_index.read_text(path).splitlines())
                if not (isinstance(a, int) and isinstance(b, int) and 1 <= a <= b <= count):
                    errors.append("%s: lines %s-%s are not inside %s (%d lines)." % (rid, a, b, f, count))
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
    for g in data.get("glossary", []):
        if not (g.get("technical_name") and g.get("business_meaning")):
            errors.append("glossary: each entry needs technical_name and business_meaning.")
    return errors + check_surroundings(data) + check_flow(data, work["id"], ids) \
        + check_requirements(data, work["id"], ids)


NUMBER_RE = re.compile(r"(?<![\w.])\d[\d,]*(?:\.\d+)?")


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
    import java_index
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


def check_flow(data, work_id, rule_ids):
    """Checks the flow steps (the diagram) and the scenarios that walk through them."""
    errors = []
    steps = [s for s in data.get("flow_steps") or [] if isinstance(s, dict)]
    if not steps:
        return ["Missing 'flow_steps': describe the flow from the entry point to every end."]
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
        if " shall " not in " %s " % q.get("text", ""):
            errors.append("%s: 'text' must be a 'shall' statement, for example: The system shall ..." % qid)
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
    if data.get("roles_basis") == "unknown" and not data.get("flow_questions_for_sme"):
        errors.append("The users and roles are unknown, so ask the SME in 'flow_questions_for_sme'.")
    return errors


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


def cmd_validate(item_id):
    path = out_dir(module_of(item_id), "work", item_id + ".json")
    if not os.path.isfile(path):
        sys.exit("Work item not found: %s" % path)
    state, errors = item_state(read_json(path))
    print("%s: %s" % (item_id, state))
    for e in errors:
        print("  - " + e)
    if errors:
        print("%d problem(s). Fix them and run validate again." % len(errors))
        sys.exit(1)


# ---------------------------------------------------------------- module overview

def documented(module):
    """Work items whose rules file passes validation, with their rules."""
    return [(w, rules) for w, state, rules, _v in gather(module) if state not in ("TODO", "EXTRACT_INVALID")]


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


def cmd_validate_overview(module):
    state, errors = overview_state(module)
    print("%s overview: %s" % (module, state))
    for e in errors:
        print("  - " + e)
    if state != "DONE":
        print("%d problem(s). Fix them and run validate-overview again." % len(errors) if errors
              else "The overview file is not written yet.")
        sys.exit(1)


# ---------------------------------------------------------------- status / next

STEP = {
    "TODO": ("extract.md", "Use Claude Sonnet (Opus for a large or confusing flow)."),
    "EXTRACT_INVALID": ("extract.md", "The rules file has problems. Run the step again."),
    "EXTRACTED": ("verify.md", "Use a different model from the extract step, in a NEW chat."),
    "VERIFY_INVALID": ("verify.md", "The verify file has problems. Run the step again in a NEW chat."),
    "DISPUTED": ("resolve.md", "Use Claude Opus, in a NEW chat."),
    "RECHECK": ("recheck.md", "Use a different model from the resolve step, in a NEW chat."),
}


def cmd_status(module, only_next=False):
    items = work_items(module)
    if not items:
        sys.exit("No work items. Run: python explain.py inventory %s" % module)
    counts, first = {}, None
    for w in items:
        state, _ = item_state(w)
        counts[state] = counts.get(state, 0) + 1
        if state != "DONE" and first is None:
            first = (w, state)
        if not only_next:
            print("%-12s %-16s %s" % (w["id"], state, w["entry_points"][0]["method"]))
    print("\n" + ", ".join("%s: %d" % kv for kv in sorted(counts.items())))
    if first is None:
        if overview_state(module)[0] != "DONE":
            print("All work items are DONE. Next: the module overview. Use Claude Opus, in a NEW chat.\n"
                  "Open a new Copilot agent chat and paste this line:\n\n  " + overview_task(module))
            return
        print("All work items are DONE. Run: python explain.py build-doc %s" % module)
        return
    w, state = first
    prompt, hint = STEP[state]
    print("\nNext: %s (%s). %s\nOpen a new Copilot agent chat and paste this line:\n" % (w["id"], state, hint))
    print("  Read %s and follow it. Work item: %s"
          % (shown(os.path.join(HERE, "steps", prompt)),
             shown(out_dir(module, "work", w["id"] + ".json"))))


# ---------------------------------------------------------------- coverage / document

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


def cmd_coverage(module):
    rows = gather(module)
    total = by_rule = none = pending = clear = unclear = 0
    lines = ["# Coverage report - %s" % module, "",
             "| Work item | State | Items | In a rule | No business rule | Not handled |", "|---|---|---|---|---|---|"]
    for w, state, rules, _v in rows:
        ids = {i["id"] for i in w["items_to_cover"]}
        covered = {c for r in (rules or {}).get("rules", []) for c in r.get("covers") or []} & ids
        nb = {e.get("item") for e in (rules or {}).get("no_business_rule", [])} & ids - covered
        if state in ("TODO", "EXTRACT_INVALID"):
            covered, nb = set(), set()
        else:
            for r in rules.get("rules", []):
                clear += r.get("status") == "clear"
                unclear += r.get("status") == "unclear"
        left = len(ids) - len(covered) - len(nb)
        total += len(ids); by_rule += len(covered); none += len(nb); pending += left
        lines.append("| %s | %s | %d | %d | %d | %d |" % (w["id"], state, len(ids), len(covered), len(nb), left))
    done = sum(1 for r in rows if r[1] == "DONE")
    pct = 100.0 * (total - pending) / total if total else 0
    head = ["", "- Work items done (extracted and verified): **%d of %d**" % (done, len(rows)),
            "- Code items handled: **%d of %d (%.1f%%)**" % (total - pending, total, pct),
            "- Explained by a rule: %d. Marked as no business rule: %d. Not handled: %d." % (by_rule, none, pending),
            "- Rules: %d clear, %d unclear (unclear rules have questions for the SME)." % (clear, unclear), ""]
    inv = read_json(out_dir(module, "inventory.json"))
    if inv["files_not_parsed"]:
        head.append("- Files the parser could not read (checked as whole files): %s" % ", ".join(inv["files_not_parsed"]))
    text = "\n".join(lines[:2] + head + lines[2:]) + "\n"
    path = out_dir(module, "coverage.md")
    open(path, "w", encoding="utf-8").write(text)
    print(text)
    print("Written: " + plain(path))


def cell(text):
    """Text that is safe inside one cell of a Markdown table."""
    return re.sub(r"\s+", " ", str(text)).strip().replace("|", "\\|")


def mermaid_text(text):
    text = re.sub(r"\s+", " ", str(text)).strip()
    for char, code in (("#", "#35;"), ('"', "#quot;"), ("<", "#lt;"), (">", "#gt;")):
        text = text.replace(char, code)
    return text


def flow_diagram(steps):
    """The flow steps as a Mermaid flowchart: rounded = start and end, diamond = decision."""
    shapes = {"decision": '{"%s"}', "step": '["%s"]'}
    lines = ["```mermaid", "flowchart TD"]
    for s in steps:
        lines.append("    %s%s" % (s["id"], shapes.get(s["kind"], '(["%s"])') % mermaid_text(s["text"])))
    for s in steps:
        if s["kind"] == "decision":
            lines += ['    %s -->|"%s"| %s' % (s["id"], mermaid_text(b["label"]), b["to"]) for b in s["branches"]]
        elif s["kind"] != "end":
            lines.append("    %s --> %s" % (s["id"], s["next"]))
    return lines + ["```", ""]


def example_lines(ex):
    lines = ["- Input: %s = %s" % kv for kv in ex["inputs"].items()] if isinstance(ex["inputs"], dict) \
        else ["- Input: %s" % i for i in ex["inputs"]]
    return lines + ["- Step: " + s for s in ex["steps"]] + ["- Result: **%s**" % ex["result"]]


def settled(verdict, state):
    """Second check passed: the reviewer agreed at once, or agreed with the text after its correction."""
    if state != "DONE":
        return False
    if needs_recheck(verdict):
        return verdict.get("recheck") == "agree"
    return verdict.get("verdict") == "agree" or verdict.get("resolution") == "verifier_wrong"


def cmd_build_doc(module):
    rows = gather(module)
    glossary, questions, fixed, body = {}, [], [], []
    trace_flows, trace_reqs, trace_rules = [], [], []
    titles, counts = {}, {"flows": 0, "scenarios": 0, "rules": 0, "requirements": 0}
    for w, state, rules, verify in rows:
        if state in ("TODO", "EXTRACT_INVALID") or not rules:
            body += ["### %s - not documented yet" % w["id"], ""]
            continue
        for g in rules.get("glossary", []):
            glossary.setdefault(g["technical_name"], g["business_meaning"])
        verify = verify or {}
        verdicts = {v.get("rule_id"): v for v in verify.get("verdicts", [])}
        sc_verdicts = {v.get("scenario_id"): v for v in verify.get("scenario_verdicts", [])}
        fr_verdicts = {v.get("requirement_id"): v for v in verify.get("requirement_verdicts", [])}
        steps = {s["id"]: s for s in rules["flow_steps"]}
        reqs, the_rules, scenarios = rules.get("requirements") or [], rules.get("rules", []), rules["scenarios"]
        # ids for the reader count through the whole module: FR-01, BR-01, SC-01
        fr = {q["id"]: "FR-%02d" % (counts["requirements"] + n) for n, q in enumerate(reqs, 1)}
        br = {r["id"]: "BR-%02d" % (counts["rules"] + n) for n, r in enumerate(the_rules, 1)}
        sc_no = {s["id"]: "SC-%02d" % (counts["scenarios"] + n) for n, s in enumerate(scenarios, 1)}
        counts["flows"] += 1
        counts["requirements"] += len(reqs)
        counts["rules"] += len(the_rules)
        counts["scenarios"] += len(scenarios)
        title = "3.%d %s" % (counts["flows"], rules["flow_title"])
        titles[w["id"]] = title
        own_questions = ["%s: %s" % (rules["flow_title"], q) for q in rules.get("flow_questions_for_sme") or []]
        mark = lambda verdict: "✔" if settled(verdict, state) else "☐"  # noqa: E731

        body += ["### " + title, ""]
        if w["kind"] == "unreached":
            body += ["> Note: no other code in this module calls this code. Confirm if it is still used.", ""]
        body += ["#### Overview", "", rules["flow_summary"], "", "**Why it exists:** " + rules["flow_purpose"], "",
                 "**Starts when:** " + rules["starts_when"], ""]

        body += ["#### Users and roles", "", "| Role | Allowed to |", "|---|---|"]
        body += ["| %s | %s |" % (cell(u["role"]), cell(u["allowed_to"])) for u in rules["users_and_roles"]]
        body += ["", REASON_BASIS[rules["roles_basis"]].strip(), ""] if REASON_BASIS[rules["roles_basis"]] else [""]

        body += ["#### Preconditions", ""] + ["- " + str(p) for p in rules["preconditions"]] + [""]

        body += ["#### Functional requirements", ""]
        for q in reqs:
            body.append("- **%s:** %s (%s) Second check %s" % (
                fr[q["id"]], q["text"], ", ".join(br[r] for r in q["rules"]), mark(fr_verdicts.get(q["id"], {}))))
            trace_reqs.append((fr[q["id"]], q["id"], ", ".join(br[r] for r in q["rules"])))
        body += [""] if reqs else ["None. This code has no business behaviour.", ""]

        body += ["#### Business rules", ""]
        for r in the_rules:
            body += ["##### %s - %s" % (br[r["id"]], r["title"]), "",
                     "**What it does:** " + r["what_it_does"], "",
                     "**Business reason:** " + r["business_reason"] + REASON_BASIS[r["reason_basis"]], "",
                     "**When it applies:**"]
            body += ["- " + c for c in r["when_it_applies"]]
            body += ["", "**How the value is calculated:** " + r["how_it_is_calculated"], "",
                     "**Values and where they come from:**", "", "| Value | Comes from | Exact value, column or formula |",
                     "|---|---|---|"]
            for v in r["values_used"]:
                body.append("| %s | %s | %s |" % (cell(v["name"]), VALUE_SOURCES[v["comes_from"]], cell(v["value"])))
                if v["comes_from"] == "fixed":
                    fixed.append((v["name"], v["value"], br[r["id"]]))
            body += ["", "**Example:**"] + example_lines(r["example"])
            if r.get("exceptions"):
                body += ["", "**Exceptions:**"] + ["- " + e for e in r["exceptions"]]
            body += ["", "**Status:** Code-checked ✔ / Second check %s / SME confirmed ☐%s"
                     % (mark(verdicts.get(r["id"], {})),
                        "  — **UNCLEAR, see open questions**" if r["status"] == "unclear" else ""), ""]
            own_questions += ["%s: %s" % (br[r["id"]], q) for q in r.get("questions_for_sme") or []]
            trace_rules.append((br[r["id"]], r["id"], "; ".join(
                "`%s` lines %s-%s" % (s["file"], s["start_line"], s["end_line"]) for s in r["sources"])))
        if not the_rules:
            body += ["None.", ""]

        def scenario_block(sc):
            used = []
            for sid in sc["path"]:
                used += [br[r] for r in steps[sid].get("rules") or [] if br[r] not in used]
            lines = ["**%s - %s**" % (sc_no[sc["id"]], sc["title"]), "", "When:"] + ["- " + c for c in sc["when"]]
            lines += ["", "Steps:"] + ["%d. %s" % (n, steps[sid]["text"]) for n, sid in enumerate(sc["path"], 1)]
            lines += ["", "Outcome: " + sc["outcome"]]
            if sc["type"] != "main":
                lines += ["", "What the user sees: " + sc["user_sees"]]
            lines += ["", "Example:"] + example_lines(sc["example"])
            return lines + ["", "Rules used: %s. Second check %s" % (", ".join(used) or "none",
                                                                     mark(sc_verdicts.get(sc["id"], {}))), ""]

        body += ["#### Main flow", ""] + flow_diagram(rules["flow_steps"])
        body += ["Second check of the diagram: %s" % mark(verify.get("flow_verdict") or {}), ""]
        for sc in scenarios:
            if sc["type"] == "main":
                body += scenario_block(sc)

        others = [sc for sc in scenarios if sc["type"] != "main"]
        body += ["#### Alternate and exception flows", ""]
        if others:
            body += ["| Scenario | Type | When | Outcome | What the user sees |", "|---|---|---|---|---|"]
            body += ["| %s %s | %s | %s | %s | %s |" % (sc_no[sc["id"]], cell(sc["title"]), sc["type"].capitalize(),
                                                      cell("; ".join(sc["when"])), cell(sc["outcome"]), cell(sc["user_sees"]))
                     for sc in others] + [""]
            for sc in others:
                body += scenario_block(sc)
        else:
            body += ["None.", ""]

        body += ["#### Inputs and outputs", "", "**Inputs:**"] + ["- " + str(i) for i in rules["inputs"]]
        body += ["", "**Outputs:**"] + ["- " + str(o) for o in rules["outputs"]]
        body += ["", "**How it can end:**"] + ["- " + s["text"] for s in rules["flow_steps"] if s["kind"] == "end"] + [""]

        still_open = [(rules["flow_title"], verify.get("flow_verdict") or {})]
        for key, names, entries in (("rule_id", br, verify.get("verdicts", [])),
                                    ("scenario_id", sc_no, verify.get("scenario_verdicts", [])),
                                    ("requirement_id", fr, verify.get("requirement_verdicts", []))):
            still_open += [(names.get(v.get(key), v.get(key)), v) for v in entries]
        still_open += [("A behaviour reported as missing (%s)" % m.get("description", ""), m)
                       for m in verify.get("missed_rules", [])]
        own_questions += ["%s: the two reviews still disagree after a correction. %s" % (name, v.get("recheck_reason", ""))
                          for name, v in still_open if v.get("recheck") == "disagree"]
        body += ["#### Open questions", ""] + (["- " + q for q in own_questions] or ["None."]) + [""]
        questions += own_questions
        trace_flows.append((title, w["id"], "; ".join(
            "`%s` (`%s` lines %s-%s)" % (e["method"], e["file"], e["start_line"], e["end_line"]) for e in w["entry_points"])))

    overview = read_json(out_dir(module, "overview.json")) if overview_state(module)[0] == "DONE" else None
    for q in reversed((overview or {}).get("questions_for_sme") or []):
        questions.insert(0, "%s module: %s" % (module, q))
    types = (overview or {}).get("flow_types", [])

    out = ["# %s - Business logic of the current system" % module, "",
           "This document describes what the current system does. It was produced from the source code.", "",
           "How to read it: chapter 1 says why the module exists. Chapter 3 has one section for each feature, "
           "always in the same order: overview, users and roles, preconditions, functional requirements, "
           "business rules, main flow, alternate and exception flows, inputs and outputs, open questions. "
           "References to the code are kept out of the text; they are in appendix A.", "",
           "Ids: **FR** = functional requirement, **BR** = business rule, **SC** = scenario.", "",
           "Status marks: **Code-checked** = passed the automatic checks. "
           "**Second check** = a second, independent review agreed. "
           "**SME confirmed** = to be ticked by the business expert.", "",
           "## 1. Module overview", "", "### Why this module exists", ""]
    if overview:
        out += [overview["module_purpose"] + (REASON_BASIS["inferred"] if overview["purpose_basis"] == "inferred" else ""), ""]
    else:
        out += ["Not written yet. It is written when all flows are documented.", ""]
    out += ["### At a glance", "", "| | Number |", "|---|---|"]
    if overview:
        out.append("| Types of feature | %d |" % len(types))
    out += ["| Features | %d |" % counts["flows"],
            "| Functional requirements | %d |" % counts["requirements"],
            "| Business rules | %d |" % counts["rules"],
            "| Scenarios (ways through a feature, from start to end) | %d |" % counts["scenarios"],
            "| Open questions for the SME | %d |" % len(questions), ""]
    if overview:
        out += ["### Types of feature", "", "```mermaid", "flowchart LR", '    M(["%s module"])' % mermaid_text(module)]
        out += ['    M --> T%d["%s<br/>%d feature%s"]' % (n, mermaid_text(t["name"]), len(t["flows"]), "s" * (len(t["flows"]) != 1))
                for n, t in enumerate(types, 1)]
        out += ["```", ""]
        for n, t in enumerate(types, 1):
            out += ["**%d. %s** - %s" % (n, t["name"], t["description"]), ""]
            out += ["- %s" % titles.get(f, f) for f in t["flows"]] + [""]
    if glossary:
        out += ["## 2. Glossary: names in the code and their business meaning", "", "| Name in code | Business meaning |", "|---|---|"]
        out += ["| `%s` | %s |" % (k, cell(glossary[k])) for k in sorted(glossary)] + [""]
    out += ["## 3. Features", ""] + body
    out += ["## 4. Fixed business values", "",
            "Values that are written in the code itself. To change one of them today, the code must be changed.", ""]
    if fixed:
        out += ["| Value | Fixed at | Used in rule |", "|---|---|---|"]
        out += ["| %s | %s | %s |" % (cell(n), cell(v), rid) for n, v, rid in fixed] + [""]
    else:
        out += ["None.", ""]
    out += ["## 5. All open questions for the SME", ""] + (["- " + q for q in questions] or ["None."]) + [""]
    out += ["## Appendix A. Where each feature, requirement and rule comes from in the code", "",
            "| Feature | Work item | Entry point in the code |", "|---|---|---|"]
    out += ["| %s | %s | %s |" % (cell(t), i, e) for t, i, e in trace_flows]
    out += ["", "| Requirement | Id in the data files | Rests on |", "|---|---|---|"]
    out += ["| %s | %s | %s |" % row for row in trace_reqs]
    out += ["", "| Rule | Id in the data files | File and lines |", "|---|---|---|"]
    out += ["| %s | %s | %s |" % row for row in trace_rules] + [""]
    path = out_dir(module, module + "-business-logic.md")
    open(path, "w", encoding="utf-8").write("\n".join(out))
    print("Written: " + plain(path))


# ---------------------------------------------------------------- run (no human in the loop)

RUNNER = {
    "command": ["claude", "-p", "--model", "{model}", "--permission-mode", "acceptEdits",
                "--allowedTools", "Read,Glob,Grep,Write,Edit"],
    "models": {"extract": "sonnet", "verify": "opus", "resolve": "opus", "recheck": "sonnet", "overview": "opus"},
    "parallel": 3,
    "max_calls_per_item": 6,
    "timeout_minutes": 30,
}


def prepare(command, argv):
    """Shared start of 'run' and 'prepare': registers the module, saves the notes, builds the inventory."""
    import argparse
    ap = argparse.ArgumentParser(prog="explain.py " + command)
    ap.add_argument("module")
    ap.add_argument("--path", nargs="+", help="module folder or folders (Java, SQL, configuration), "
                                              "relative to source_root (adds them to config.json)")
    ap.add_argument("--about", help="what the business team knows about this module")
    ap.add_argument("--about-file", help="the same, read from a text file")
    ap.add_argument("--parallel", type=int)
    opts = ap.parse_args(argv)
    module = opts.module

    cfg_path = os.path.join(HERE, "config.json")
    if opts.path:
        raw = read_json(cfg_path)
        paths = [p.replace("\\", "/") for p in opts.path]
        raw.setdefault("modules", {})[module] = paths[0] if len(paths) == 1 else paths
        write_json(cfg_path, raw)
    cfg = load_config()
    if module not in cfg["modules"]:
        sys.exit("Module '%s' is not listed in config.json. Give its folder with --path." % module)

    info_path = out_dir(module, "module-info.md")
    about = read_text_file(opts.about_file) if opts.about_file else opts.about
    if about:
        os.makedirs(os.path.dirname(info_path), exist_ok=True)
        open(info_path, "w", encoding="utf-8").write(about)
    elif os.path.isfile(info_path):
        about = read_text_file(info_path)

    if not work_items(module):
        cmd_inventory(module)
    return opts, cfg, about


# ---------------------------------------------------------------- prepare / step (driven from Copilot Chat)

def cmd_prepare(argv):
    opts, cfg, _about = prepare("prepare", argv)
    module = opts.module
    write_json(out_dir(module, "source-hashes.json"), snapshot(module_dirs(cfg, module), cfg["source_root"]))
    write_json(out_dir(module, "attempts.json"), {})
    print("PREPARED: %s, %d work items. Now repeat: python explain.py step %s" % (module, len(work_items(module)), module))


def cmd_step(module):
    """Prints the next task for the chat agent, or FINISHED. The chat repeats this until FINISHED."""
    cfg = load_config()
    base_path = out_dir(module, "source-hashes.json")
    if not os.path.isfile(base_path):
        sys.exit("Run first: python explain.py prepare %s" % module)
    before = read_json(base_path)
    now = snapshot(module_dirs(cfg, module), cfg["source_root"])
    changed = sorted(f for f in set(before) | set(now) if before.get(f) != now.get(f))
    if changed:
        print("STOP: source files changed since prepare. Restore them, then run prepare again.")
        for f in changed:
            print("  " + f)
        sys.exit(1)

    limit = dict(RUNNER, **cfg.get("runner", {}))["max_calls_per_item"]
    attempts_path = out_dir(module, "attempts.json")
    attempts = read_json(attempts_path)
    chosen, stuck, left = None, [], 0
    for w in work_items(module):
        state, _errors = item_state(w)
        if state == "DONE":
            continue
        if attempts.get(w["id"], 0) >= limit:
            stuck.append((w["id"], state))
            continue
        left += 1
        chosen = chosen or (w, state)
    info_note = ""
    if os.path.isfile(out_dir(module, "module-info.md")):
        info_note = " First read %s: it is what the business team says about this module. Use it for names " \
                    "and meaning; if the code does something different, the code wins and you add a question " \
                    "for the SME." % shown(out_dir(module, "module-info.md"))
    if chosen is None:
        # every flow is done or stuck: the module overview is the last task
        key, (ostate, _errors) = module + "-overview", overview_state(module)
        if ostate.startswith("OVERVIEW") and attempts.get(key, 0) >= limit:
            stuck.append((key, ostate))
        elif ostate.startswith("OVERVIEW"):
            attempts[key] = attempts.get(key, 0) + 1
            write_json(attempts_path, attempts)
            record_path = out_dir(module, "runs", key + ".json")
            records = read_json(record_path) if os.path.isfile(record_path) else []
            records.append({
                "step": "overview", "runner": "copilot-chat", "agent": "explainer-overview",
                "started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "prompt_sha256": prompt_hash("overview.md"), "state_before": ostate,
            })
            write_json(record_path, records)
            task = overview_task(module)
            if ostate == "OVERVIEW_INVALID":
                task += " The file from the last attempt failed validation: run `python explain.py " \
                        "validate-overview %s`, fix those problems in the file and keep what is right." % module
            print("REMAINING: module overview")
            print("AGENT: explainer-overview")
            print("TASK: " + task + info_note)
            return
        cmd_coverage(module)
        cmd_build_doc(module)
        for item_id, state in stuck:
            print("STUCK: %s stopped at %s after %d attempts." % (item_id, state, limit))
        print("FINISHED")
        return

    w, state = chosen
    step = STEP[state][0][:-3]
    attempts[w["id"]] = attempts.get(w["id"], 0) + 1
    write_json(attempts_path, attempts)
    record_path = out_dir(module, "runs", w["id"] + ".json")
    records = read_json(record_path) if os.path.isfile(record_path) else []
    records.append({
        "step": step, "runner": "copilot-chat", "agent": "explainer-" + step,
        "started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "prompt_sha256": prompt_hash(STEP[state][0]),
        "source_sha256": {f: before.get(f) for f in
                          sorted({m["file"] for m in w["methods_to_document"] + w["context_methods"]})},
        "state_before": state,
    })
    write_json(record_path, records)
    task = "Read %s and follow it. Work item: %s" % (shown(os.path.join(HERE, "steps", STEP[state][0])),
                                                    shown(out_dir(module, "work", w["id"] + ".json")))
    if state.endswith("_INVALID"):
        task += " The file from the last attempt failed validation: run `python explain.py validate %s`, " \
                "fix those problems in the file and keep what is right." % w["id"]
    print("REMAINING: %d work items" % left)
    print("AGENT: explainer-%s" % step)
    print("TASK: " + task + info_note)


def cmd_run(argv):
    import shutil
    import subprocess
    import threading
    from concurrent.futures import ThreadPoolExecutor

    opts, cfg, about = prepare("run", argv)
    module = opts.module
    runner = dict(RUNNER, **cfg.get("runner", {}))
    models = dict(RUNNER["models"], **runner.get("models", {}))
    exe = shutil.which(runner["command"][0])
    if not exe:
        sys.exit("Command not found: %s. Set runner.command in config.json." % runner["command"][0])
    items = work_items(module)
    root = plain(cfg["source_root"])
    extra = [] if not os.path.relpath(HERE, cfg["source_root"]).startswith("..") else ["--add-dir", plain(HERE)]
    lock, stop = threading.Lock(), threading.Event()
    dirs = module_dirs(cfg, module)
    before = snapshot(dirs, cfg["source_root"])

    def say(text):
        with lock:
            print(text, flush=True)

    def prompt_for(first_line, errors):
        lines = [first_line, "",
                 "You are running with no human present. Do not ask questions; decide and write the file.",
                 "Do not run explain.py. The runner validates your file after you finish."]
        if about:
            lines += ["", "What the business team says about this module. Use it for names and meaning. "
                          "If the code does something different, the code wins and you add a question for the SME:",
                      about.strip()]
        if errors:
            lines += ["", "The file from the last attempt exists and failed validation. "
                          "Fix these problems in it and keep what is right:"]
            lines += ["- " + e for e in errors]
        return "\n".join(lines)

    def call(step, prompt, log):
        """One model call. Returns the facts for the run record, and the source files it changed."""
        os.makedirs(os.path.dirname(log), exist_ok=True)
        args = runner["command"][1:]
        # a tool that takes its prompt as an argument gets a one-line pointer to a prompt file instead of stdin
        if any("{prompt_file}" in a for a in args):
            prompt_file = log[:-4] + ".prompt.md"
            open(prompt_file, "w", encoding="utf-8").write(prompt)
            args = [a.replace("{prompt_file}", shown(prompt_file)) for a in args]
            feed = {"stdin": subprocess.DEVNULL}
        else:
            feed = {"input": prompt}
        cmd = [exe] + [a.replace("{model}", models[step]) for a in args] + extra
        started, exit_code = time.time(), None
        try:
            done = subprocess.run(cmd, cwd=root, capture_output=True, encoding="utf-8", errors="replace",
                                  timeout=runner["timeout_minutes"] * 60, **feed)
            exit_code = done.returncode
            text = "exit code %d\n\n%s\n%s" % (done.returncode, done.stdout, done.stderr)
        except subprocess.TimeoutExpired:
            text = "timed out after %d minutes" % runner["timeout_minutes"]
        open(log, "w", encoding="utf-8").write(text)
        now = snapshot(dirs, cfg["source_root"])
        changed = sorted(f for f in set(before) | set(now) if before.get(f) != now.get(f))
        if changed:
            stop.set()
        return {"step": step, "model": models[step], "command": runner["command"],
                "started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(started)),
                "seconds": round(time.time() - started, 1), "exit_code": exit_code,
                "source_files_changed": changed}, changed

    def run_item(w):
        calls = 0
        state, errors = item_state(w)
        record_path = out_dir(module, "runs", w["id"] + ".json")
        records = read_json(record_path) if os.path.isfile(record_path) else []
        own_files = sorted({m["file"] for m in w["methods_to_document"] + w["context_methods"]})
        while state != "DONE" and calls < runner["max_calls_per_item"] and not stop.is_set():
            step = STEP[state][0][:-3]
            calls += 1
            say("%s: %s -> %s (%s, call %d)" % (w["id"], state, step, models[step], calls))
            first_line = "Read %s and follow it. Work item: %s" % (
                shown(os.path.join(HERE, "steps", STEP[state][0])), shown(out_dir(module, "work", w["id"] + ".json")))
            record, changed = call(step, prompt_for(first_line, errors),
                                   out_dir(module, "logs", "%s-%d-%s.txt" % (w["id"], calls, step)))
            new_state, errors = item_state(w)
            records.append(dict(record, prompt_sha256=prompt_hash(STEP[state][0]),
                                source_sha256={f: before.get(f) for f in own_files},
                                state_before=state, state_after=new_state))
            write_json(record_path, records)
            if changed:
                say("%s: STOPPED. Source files changed during this call:\n  %s\n"
                    "Restore them, then run again. No further model calls will start." % (w["id"], "\n  ".join(changed)))
                return w["id"], "SOURCE_CHANGED", calls
            state = new_state
        return w["id"], state, calls

    def run_overview():
        """The last task: why the module exists and its types of flow, written from the documented flows."""
        key, calls = module + "-overview", 0
        state, errors = overview_state(module)
        record_path = out_dir(module, "runs", key + ".json")
        records = read_json(record_path) if os.path.isfile(record_path) else []
        while state.startswith("OVERVIEW") and calls < runner["max_calls_per_item"] and not stop.is_set():
            calls += 1
            say("%s: %s -> overview (%s, call %d)" % (key, state, models["overview"], calls))
            record, changed = call("overview", prompt_for(overview_task(module), errors),
                                   out_dir(module, "logs", "%s-%d-overview.txt" % (key, calls)))
            new_state, errors = overview_state(module)
            records.append(dict(record, prompt_sha256=prompt_hash("overview.md"),
                                state_before=state, state_after=new_state))
            write_json(record_path, records)
            if changed:
                say("%s: STOPPED. Source files changed during this call:\n  %s" % (key, "\n  ".join(changed)))
                return key, "SOURCE_CHANGED", calls
            state = new_state
        return key, ("DONE" if state == "NONE" else state), calls

    with ThreadPoolExecutor(opts.parallel or runner["parallel"]) as pool:
        results = list(pool.map(run_item, items))
    overview = run_overview()

    print()
    cmd_coverage(module)
    cmd_build_doc(module)
    stuck = [r for r in results if r[1] != "DONE"]
    print("\n%d of %d work items DONE, %d model calls." % (len(results) - len(stuck), len(results),
                                                         sum(r[2] for r in results) + overview[2]))
    if overview[1] != "DONE":
        stuck.append(overview)
    for item_id, state, _calls in stuck:
        print("  %s stopped at %s. See %s" % (item_id, state, plain(out_dir(module, "logs"))))
    sys.exit(1 if stuck else 0)


def read_text_file(path):
    with open(path, encoding="utf-8-sig") as fh:
        return fh.read()


def file_hash(path):
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def snapshot(dirs, source_root):
    """Hash of every file in the module folders, keyed like the 'file' fields of a work item."""
    hashes = {}
    for module_dir in dirs:
        for dirpath, _dirs, names in os.walk(module_dir):
            if dirpath.startswith(os.path.join(HERE, "output")):  # the pipeline's own output is allowed to change
                continue
            for name in names:
                path = os.path.join(dirpath, name)
                hashes[os.path.relpath(path, source_root).replace("\\", "/")] = file_hash(path)
    return hashes


def prompt_hash(step_file):
    """One hash for the instructions a step was given: the common rules plus the step prompt."""
    h = hashlib.sha256()
    for name in ("common-rules.md", step_file):
        with open(os.path.join(HERE, "steps", name), "rb") as fh:
            h.update(fh.read())
    return h.hexdigest()


# ---------------------------------------------------------------- selfcheck

def cmd_selfcheck():
    ok = True

    def report(good, text):
        nonlocal ok
        ok = ok and good
        print(("[ OK ] " if good else "[FAIL] ") + text)

    report(sys.version_info >= (3, 7), "Python %s (3.7 or newer is needed)" % sys.version.split()[0])
    try:
        import java_index  # noqa: F401
        report(True, "Java parser library loads from the vendor folder")
    except Exception as exc:
        report(False, "Java parser library does not load: %s" % exc)
    try:
        cfg = load_config()
        report(os.path.isdir(cfg["source_root"]), "source_root exists: %s" % cfg["source_root"])
        for name in cfg["modules"]:
            for path in module_dirs(cfg, name):
                n = sum(bool(java_index.file_type(f, cfg.get("file_types")))
                        for _d, _s, fs in os.walk(path) for f in fs)
                report(n > 0, "module %s: %d Java, SQL and configuration files in %s" % (name, n, path))
        inside = not os.path.relpath(HERE, cfg["source_root"]).startswith("..")
        report(inside, "pipeline folder is inside source_root, so the Copilot agent can read both")
    except Exception as exc:
        report(False, "config.json cannot be read: %s" % exc)
    print("\nAll checks passed." if ok else "\nFix the FAIL lines before you continue.")
    sys.exit(0 if ok else 1)


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    flags = {a for a in sys.argv[1:] if a.startswith("--")}
    if not args:
        sys.exit(__doc__)
    sys.path.insert(0, SCRIPTS)
    cmd, rest = args[0], args[1:]
    if cmd == "selfcheck":
        cmd_selfcheck()
    elif cmd == "run":
        cmd_run(sys.argv[2:])
    elif cmd == "prepare":
        cmd_prepare(sys.argv[2:])
    elif len(rest) != 1:
        sys.exit(__doc__)
    elif cmd == "step":
        cmd_step(rest[0])
    elif cmd == "inventory":
        cmd_inventory(rest[0], force="--force" in flags)
    elif cmd == "next":
        cmd_status(rest[0], only_next=True)
    elif cmd == "status":
        cmd_status(rest[0])
    elif cmd == "validate-overview":
        cmd_validate_overview(rest[0])
    elif cmd == "validate":
        cmd_validate(rest[0])
    elif cmd == "coverage":
        cmd_coverage(rest[0])
    elif cmd == "build-doc":
        cmd_build_doc(rest[0])
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
