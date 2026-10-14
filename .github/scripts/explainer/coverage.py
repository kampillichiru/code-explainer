"""The coverage report, and the facts every report repeats: what is still a draft, which files were
not read, what the execution check did."""

import os

from . import java_index, run_check
from .state import gather
from .store import HERE, load_config, module_dirs, out_dir, plain, read_json, work_items


def unread_files(module):
    """Files in the module folders that the tool does not read: {extension: [paths]}. Looked up fresh each time."""
    cfg = load_config()
    return java_index.files_not_read(cfg["source_root"], module_dirs(cfg, module), cfg.get("file_types"),
                                     skip=os.path.join(HERE, "output"))


def unread_lines(module, examples=3):
    """The files that were not read, as Markdown: one table row for each file type. Empty if every file was read."""
    found = unread_files(module)
    if not found:
        return []
    order = sorted(found, key=lambda e: (e not in java_index.LOGIC_EXTS, -len(found[e]), e))
    risky = sum(len(found[e]) for e in found if e in java_index.LOGIC_EXTS)
    lines = ["**%d file(s) in the module folders were not read**, %d of them of a type that often holds business "
             "logic. Nothing in this document comes from them. To have a type read, add its extension to "
             "`file_types` in `config.json` (as `java`, `sql` or `config`) and run the inventory again; otherwise "
             "confirm with the SME that these files hold no business rule." % (sum(map(len, found.values())), risky), "",
             "| File type | Files | May hold business logic | Examples |", "|---|---|---|---|"]
    for ext in order:
        paths = found[ext]
        more = " and %d more" % (len(paths) - examples) if len(paths) > examples else ""
        lines.append("| `%s` | %d | %s | %s%s |" % (ext, len(paths), "**Yes**" if ext in java_index.LOGIC_EXTS else "Unlikely",
                                                 ", ".join("`%s`" % p for p in paths[:examples]), more))
    return lines + [""]


def execution_line(module):
    """One line for the reports: can code of this module be run, and how many examples were."""
    path = out_dir(module, "exec", "setup.json")
    if not os.path.isfile(path):
        return "Execution check: not set up for this module (its inventory was made by an older version)."
    setup = read_json(path)
    if not setup["available"]:
        return "Execution check: not available. %s Examples are checked by the second reviewer only." % setup["reason"]
    states = [r.get("status") for w in work_items(module)
              for r in run_check.results(out_dir(module, "exec"), w["id"]).values()]
    line = "Execution check: %d piece(s) of code can be run on their own; %d example(s) were run and returned the " \
           "documented result." % (setup["runnable_methods"], states.count("match"))
    if states.count("not_run"):
        line += " %d example(s) could not be run." % states.count("not_run")
    if setup["does_not_compile"]:
        line += " %d file(s) do not compile without their libraries (set execution.classpath in config.json)." \
                % len(setup["does_not_compile"])
    return line


def draft_banner(rows):
    """Lines that mark the output as a draft while any work item is not DONE. Empty when all are DONE."""
    not_done = ["%s (%s)" % (w["id"], state) for w, state, _r, _v in rows if state != "DONE"]
    if not not_done:
        return []
    return ["> **DRAFT - NOT READY TO USE AS REQUIREMENTS.** %d of %d work items have not passed the second "
            "check: %s. Their text has not been compared with the code by a second reviewer and may be wrong. "
            "Run the pipeline again to finish them; finished work items are skipped."
            % (len(not_done), len(rows), ", ".join(not_done)), ""]


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
    checked = sum(len(r[0]["items_to_cover"]) for r in rows if r[1] == "DONE")
    pct = 100.0 * (total - pending) / total if total else 0
    head = [""] + draft_banner(rows) + [
            "- Work items done (extracted and verified): **%d of %d**" % (done, len(rows)),
            "- Code items in a work item that passed the second check: **%d of %d (%.1f%%)**"
            % (checked, total, 100.0 * checked / total if total else 0),
            "- Code items explained by the first pass (not checked until the line above says so): "
            "%d of %d (%.1f%%)" % (total - pending, total, pct),
            "- Explained by a rule: %d. Marked as no business rule: %d. Not handled: %d." % (by_rule, none, pending),
            "- Rules: %d clear, %d unclear (unclear rules have questions for the SME)." % (clear, unclear),
            "- " + execution_line(module), ""]
    inv = read_json(out_dir(module, "inventory.json"))
    if inv["files_not_parsed"]:
        head.append("- Files the parser could not read (checked as whole files): %s" % ", ".join(inv["files_not_parsed"]))
    unread = unread_lines(module, examples=10)
    tail = ["", "## Files that were not read", ""] + (unread or ["None. Every file in the module folders was read."])
    text = "\n".join(lines[:2] + head + lines[2:] + tail) + "\n"
    path = out_dir(module, "coverage.md")
    open(path, "w", encoding="utf-8").write(text)
    print(text)
    print("Written: " + plain(path))
