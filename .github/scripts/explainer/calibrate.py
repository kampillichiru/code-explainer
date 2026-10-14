"""Calibration: measures the document of one module against the rules a business expert (SME) listed on their own.

  python explain.py calibrate MODULE --sme-file FILE   takes the SME's list, prints the task for the AI agent
  python explain.py calibrate MODULE --run             the same, and calls the model itself (terminal mode)
  python explain.py calibrate MODULE                   checks the comparison and writes calibration.md

Python takes the list in, checks the comparison and counts. An AI agent does the one part that needs
understanding: deciding which rule of the document says the same as which rule of the SME.
"""
import argparse
import csv
import os
import re
import shutil
import sys

from . import java_index, run_check
from .markdown import cell
from .pipeline import RUNNER, runner_settings
from .state import documented, item_state
from .store import (
    HERE,
    load_config,
    module_dirs,
    out_dir,
    plain,
    read_json,
    read_text_file,
    shown,
    under,
    work_items,
    write_json,
)

VERDICTS = ("same", "differs", "missing")
SUPPORTS = {"document": "The code agrees with the document", "sme": "The code agrees with the SME",
            "neither": "The code agrees with neither"}


def folder(module, *parts):
    return out_dir(module, "calibration", *parts)


# ---------------------------------------------------------------- the SME's list

def read_sme_file(path):
    """One rule per line of a text file, or one rule per row of a CSV file. Returns the rule texts."""
    text = read_text_file(path)
    if path.lower().endswith(".csv"):
        rows = [r for r in csv.reader(text.splitlines()) if any(c.strip() for c in r)]
        if not rows:
            return []
        head = [c.strip().lower() for c in rows[0]]
        column = next((n for n, c in enumerate(head) if "rule" in c), None)
        if column is not None:
            rows = rows[1:]
        else:  # no heading: the rule is the longest column, so that a column of numbers is not taken for it
            width = max(len(r) for r in rows)
            column = max(range(width), key=lambda n: sum(len(r[n]) for r in rows if n < len(r)))
        return [r[column].strip() for r in rows if column < len(r) and r[column].strip()]
    rules = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        rules.append(re.sub(r"^(?:[-*•]|\d+[.)])\s+", "", line))
    return rules


def ingest(module, path):
    if not os.path.isfile(path):
        sys.exit("File not found: %s" % path)
    rules = read_sme_file(path)
    if not rules:
        sys.exit("No rules found in %s. Write one rule on each line, or one in each row of a CSV file." % path)
    write_json(folder(module, "sme-rules.json"),
                 [{"id": "SME-%02d" % n, "text": t} for n, t in enumerate(rules, 1)])
    if os.path.isfile(folder(module, "result.json")):
        os.remove(folder(module, "result.json"))  # a comparison with the old list
    print("Taken in: %d rules of the SME from %s" % (len(rules), path))


def document_rules(module):
    """Every rule of the document, in the short form the comparison needs."""
    out = []
    for w, rules in documented(module):
        for r in rules.get("rules", []):
            out.append({
                "id": r["id"], "feature": rules["flow_title"], "title": r["title"], "what_it_does": r["what_it_does"],
                "when_it_applies": r["when_it_applies"], "how_it_is_calculated": r["how_it_is_calculated"],
                "exceptions": r.get("exceptions") or [],
                "values": ["%s: %s" % (v["name"], v["value"]) for v in r["values_used"]
                           if v["comes_from"] in ("fixed", "config")],
                "requirements": [q["text"] for q in rules.get("requirements") or [] if r["id"] in q["rules"]],
                "sources": r["sources"],
            })
    return out


# ---------------------------------------------------------------- check the comparison

def check_result(module):
    """Returns (errors, comparisons). An empty error list means the comparison can be counted."""
    try:
        data = read_json(folder(module, "result.json"))
    except Exception as exc:
        return ["The result file is not valid JSON: %s" % exc], []
    cfg = load_config()
    root = cfg["source_root"]
    sme = {r["id"] for r in read_json(folder(module, "sme-rules.json"))}
    known = {r["id"] for r in document_rules(module)}
    errors, seen = [], set()
    rows = [c for c in data.get("comparisons") or [] if isinstance(c, dict)]

    def lines_ok(c, who):
        f, a, b = c.get("file"), c.get("start_line"), c.get("end_line")
        path = under(root, str(f))
        if not f or not os.path.isfile(path):
            errors.append("%s: 'file' must be a source file of the module (got '%s')." % (who, f))
            return
        count = len(java_index.read_text(path).splitlines())
        if not (isinstance(a, int) and isinstance(b, int) and 1 <= a <= b <= count):
            errors.append("%s: lines %s-%s are not inside %s (%d lines)." % (who, a, b, f, count))

    for c in rows:
        sid = c.get("sme_id")
        if sid not in sme:
            errors.append("'%s' is not an id of the SME's list." % sid)
            continue
        if sid in seen:
            errors.append("%s: compared twice." % sid)
        seen.add(sid)
        verdict = c.get("verdict")
        if verdict not in VERDICTS:
            errors.append("%s: 'verdict' must be same, differs or missing." % sid)
            continue
        if verdict in ("same", "differs"):
            ids = c.get("document_rules") or []
            if not ids:
                errors.append("%s: 'document_rules' is needed: the rule ids of the document that say it." % sid)
            for i in ids:
                if i not in known:
                    errors.append("%s: '%s' is not a rule of the document." % (sid, i))
        if verdict == "differs":
            if not str(c.get("difference", "")).strip():
                errors.append("%s: 'difference' is needed: what the SME says and what the document says." % sid)
            if c.get("code_supports") not in SUPPORTS:
                errors.append("%s: 'code_supports' must be document, sme or neither. Read the code to decide." % sid)
            lines_ok(c, sid)
        if verdict == "missing":
            if not isinstance(c.get("found_in_code"), bool):
                errors.append("%s: 'found_in_code' must be true or false. Search the code of the module." % sid)
            elif c["found_in_code"]:
                lines_ok(c, sid)
            elif not c.get("searched_for"):
                errors.append("%s: 'searched_for' is needed: the words, values and names you searched the code for." % sid)
            if not str(c.get("note", "")).strip():
                errors.append("%s: 'note' is needed: one sentence on what you found." % sid)
    for sid in sorted(sme - seen):
        errors.append("%s: not compared." % sid)
    return errors, rows


# ---------------------------------------------------------------- report

def pct(part, whole):
    return "%.0f%%" % (100.0 * part / whole) if whole else "-"


def write_report(module, rows):
    sme = {r["id"]: r["text"] for r in read_json(folder(module, "sme-rules.json"))}
    doc = {r["id"]: r for r in document_rules(module)}
    states = [item_state(w)[0] for w in work_items(module)]
    same = [c for c in rows if c["verdict"] == "same"]
    differs = [c for c in rows if c["verdict"] == "differs"]
    wrong = [c for c in differs if c["code_supports"] == "sme"]
    surprise = [c for c in differs if c["code_supports"] == "document"]
    open_ = [c for c in differs if c["code_supports"] == "neither"]
    missed = [c for c in rows if c["verdict"] == "missing" and c["found_in_code"]]
    outside = [c for c in rows if c["verdict"] == "missing" and not c["found_in_code"]]
    named = {i for c in same + differs for i in c["document_rules"]}
    unlisted = [r for i, r in doc.items() if i not in named]
    in_code, found = len(sme) - len(outside), len(same) + len(differs)

    def rule_links(c):
        return ", ".join("%s (%s)" % (i, cell(doc[i]["title"])) for i in c["document_rules"])

    def where(c):
        return "`%s` lines %s-%s" % (c["file"], c["start_line"], c["end_line"])

    out = ["# Calibration report - %s" % module, "",
           "The business expert (SME) listed the rules of this module without looking at the document. This report "
           "compares that list with the document, to show how far the document can be trusted.", ""]
    if any(s != "DONE" for s in states):
        out += ["> **The document is a draft:** %d of %d work items have not passed the second check. Run the "
                "calibration again when they have; these numbers will change." % (sum(s != "DONE" for s in states), len(states)), ""]
    out += ["## Result", "",
            "| | Rules | What it means |", "|---|---|---|",
            "| Rules listed by the SME | %d | |" % len(sme),
            "| In the document, same meaning | %d | The document is right. |" % len(same),
            "| In the document, but different - the code agrees with the SME | %d | **The document is wrong.** |" % len(wrong),
            "| In the document, but different - the code agrees with the document | %d | The system does not do what the SME expects. A finding for the business, not an error of the tool. |" % len(surprise),
            "| In the document, but different - the code agrees with neither | %d | For the SME to decide. |" % len(open_),
            "| Not in the document, but found in the code | %d | **Missed by the tool.** |" % len(missed),
            "| Not in the document, and not found in the code | %d | Probably done outside this module, or by hand. |" % len(outside),
            "| Rules of the document that the SME did not list | %d of %d | To confirm: logic the SME forgot, or a rule that is not real. |" % (len(unlisted), len(doc)),
            "",
            "- **Missed: %d of %d** rules that are in the code of this module (%s)." % (len(missed), in_code, pct(len(missed), in_code)),
            "- **Wrong: %d of %d** rules that the document does have (%s)." % (len(wrong), found, pct(len(wrong), found)),
            ""]
    if not missed and not wrong:
        out += ["On this module the tool missed none of the rules the SME listed and got none of them wrong. "
                "That says nothing yet about the %d rule(s) the SME did not list: they still need a look." % len(unlisted), ""]
    else:
        out += ["Expect about the same share of missed and wrong rules in other modules of the same kind of code, "
                "and plan the SME review of those modules for it. Each case below shows where the tool went wrong.", ""]
    out += ["The comparison itself was made by an AI agent and checked for form only. Read the tables before you "
            "use the numbers: a wrong match changes them.", ""]

    def section(title, cases, head, row):
        lines = ["## %s" % title, ""]
        if not cases:
            return lines + ["None.", ""]
        return lines + [head, "|" + "---|" * head.count("|", 1)] + [row(c) for c in cases] + [""]

    out += section("Missed by the tool: in the code, not in the document", missed,
                   "| SME rule | Where it is in the code | Note |",
                   lambda c: "| %s: %s | %s | %s |" % (c["sme_id"], cell(sme[c["sme_id"]]), where(c), cell(c["note"])))
    out += section("Wrong in the document: the code agrees with the SME", wrong,
                   "| SME rule | Rule of the document | Difference | Code |",
                   lambda c: "| %s: %s | %s | %s | %s |" % (c["sme_id"], cell(sme[c["sme_id"]]), rule_links(c), cell(c["difference"]), where(c)))
    out += section("The system does not do what the SME expects", surprise,
                   "| SME rule | Rule of the document | Difference | Code |",
                   lambda c: "| %s: %s | %s | %s | %s |" % (c["sme_id"], cell(sme[c["sme_id"]]), rule_links(c), cell(c["difference"]), where(c)))
    out += section("Different, and the code does not settle it", open_,
                   "| SME rule | Rule of the document | Difference | Code |",
                   lambda c: "| %s: %s | %s | %s | %s |" % (c["sme_id"], cell(sme[c["sme_id"]]), rule_links(c), cell(c["difference"]), where(c)))
    out += section("Not found in the code of this module", outside,
                   "| SME rule | Searched for | Note |",
                   lambda c: "| %s: %s | %s | %s |" % (c["sme_id"], cell(sme[c["sme_id"]]),
                                                    cell(", ".join(map(str, c["searched_for"]))), cell(c["note"])))
    out += section("Rules of the document that the SME did not list", unlisted,
                   "| Rule | Feature | What it does | Code | Real rule? |",
                   lambda r: "| %s: %s | %s | %s | %s | ☐ |" % (
                       r["id"], cell(r["title"]), cell(r["feature"]), cell(r["what_it_does"]),
                       "; ".join("`%s` lines %s-%s" % (s["file"], s["start_line"], s["end_line"]) for s in r["sources"])))
    out += section("Same in both", same, "| SME rule | Rule of the document |",
                   lambda c: "| %s: %s | %s |" % (c["sme_id"], cell(sme[c["sme_id"]]), rule_links(c)))
    path = folder(module, "calibration.md")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(out))
    print("Calibration of %s: %d SME rules. Missed: %d of %d (%s). Wrong: %d of %d (%s). "
          "Not listed by the SME: %d of %d document rules."
          % (module, len(sme), len(missed), in_code, pct(len(missed), in_code), len(wrong), found,
             pct(len(wrong), found), len(unlisted), len(doc)))
    print("Written: " + plain(path))


# ---------------------------------------------------------------- command

def task_line(module):
    cfg = load_config()
    dirs = ", ".join(shown(d) for d in module_dirs(cfg, module))
    return ("Read %s and follow it. Module: %s. Module folders: %s. SME rules: %s. Document rules: %s. Output file: %s"
            % (shown(os.path.join(HERE, "steps", "calibrate.md")), module, dirs,
               shown(folder(module, "sme-rules.json")), shown(folder(module, "document-rules.json")),
               shown(folder(module, "result.json"))))


def call_model(module, prompt, attempt):
    """One call of the model command of config.json (the same command the 'run' mode uses)."""
    cfg = load_config()
    runner = runner_settings(cfg)
    model = dict(RUNNER["models"], **runner.get("models", {})).get("calibrate", "opus")
    exe = shutil.which(runner["command"][0])
    if not exe:
        sys.exit("Command not found: %s. Set runner.command in config.json, or leave out --run." % runner["command"][0])
    log = out_dir(module, "logs", "%s-calibrate-%d.txt" % (module, attempt))
    os.makedirs(os.path.dirname(log), exist_ok=True)
    args = runner["command"][1:]
    if any("{prompt_file}" in a for a in args):
        prompt_file = log[:-4] + ".prompt.md"
        with open(prompt_file, "w", encoding="utf-8") as fh:
            fh.write(prompt)
        args = [a.replace("{prompt_file}", shown(prompt_file)) for a in args]
        feed = None
    else:
        feed = prompt
    extra = [] if not os.path.relpath(HERE, cfg["source_root"]).startswith("..") else ["--add-dir", plain(HERE)]
    cmd = [exe] + [a.replace("{model}", model) for a in args] + extra
    code, said, complained = run_check.run_limited(cmd, plain(cfg["source_root"]), runner["timeout_minutes"] * 60, feed)
    if code is None:
        text = "timed out after %g minutes and was stopped\n\n%s\n%s" % (runner["timeout_minutes"], said, complained)
    else:
        text = "exit code %d\n\n%s\n%s" % (code, said, complained)
    with open(log, "w", encoding="utf-8") as fh:
        fh.write(text)
    return code, log


def cmd_calibrate(argv):
    ap = argparse.ArgumentParser(prog="explain.py calibrate")
    ap.add_argument("module")
    ap.add_argument("--sme-file", help="the rules the SME listed: a text file with one rule on each line, or a CSV file")
    ap.add_argument("--run", action="store_true", help="call the model command of config.json for the comparison")
    opts = ap.parse_args(argv)
    module = opts.module
    if not documented(module):
        sys.exit("Nothing is documented for %s yet. Run the module first, then calibrate." % module)
    if opts.sme_file:
        ingest(module, opts.sme_file)
    if not os.path.isfile(folder(module, "sme-rules.json")):
        sys.exit("Give the list of the SME with --sme-file. One rule on each line, written without looking at the document.")
    write_json(folder(module, "document-rules.json"), document_rules(module))

    def state():
        if not os.path.isfile(folder(module, "result.json")):
            return ["The comparison is not written yet."], []
        return check_result(module)

    errors, rows = state()
    attempt = 0
    while errors and opts.run and attempt < 3:
        attempt += 1
        lines = [task_line(module), "", "You are running with no human present. Do not ask questions; decide and "
                 "write the file.", "Do not run explain.py. The runner validates your file after you finish."]
        if os.path.isfile(folder(module, "result.json")):
            lines += ["", "The file from the last attempt exists and failed validation. Fix these problems in it "
                          "and keep what is right:"] + ["- " + e for e in errors]
        print("%s: calibrate (call %d)" % (module, attempt), flush=True)
        code, log = call_model(module, "\n".join(lines), attempt)
        before, (errors, rows) = errors, state()
        if code not in (0, None) and errors == before:
            sys.exit("The model command failed and wrote nothing. This is a usage limit, a login or a network "
                     "problem. See %s" % plain(log))
    if errors:
        if opts.run:
            print("The comparison still has %d problem(s) after %d calls:" % (len(errors), attempt))
            for e in errors:
                print("  - " + e)
            sys.exit(1)
        task = task_line(module)
        if os.path.isfile(folder(module, "result.json")):
            task += " The file from the last attempt failed validation: run `python explain.py calibrate %s`, fix " \
                    "the problems it lists in the file and keep what is right." % module
            for e in errors:
                print("  - " + e)
        print("AGENT: explainer-calibrate")
        print("TASK: " + task)
        return
    write_report(module, rows)
