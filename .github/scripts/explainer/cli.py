"""The command line: reads the command and hands over to the module that does the work."""

import os
import sys

from . import java_index, run_check
from .calibrate import cmd_calibrate
from .coverage import cmd_coverage
from .document import cmd_build_doc
from .inventory import cmd_inventory
from .pipeline import cmd_prepare, cmd_step
from .runner import cmd_run
from .state import item_state, overview_state
from .store import HERE, load_config, module_dirs, module_of, out_dir, read_json, work_items
from .tasks import STEP, item_task, overview_task


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


def cmd_validate_overview(module):
    state, errors = overview_state(module)
    print("%s overview: %s" % (module, state))
    for e in errors:
        print("  - " + e)
    if state != "DONE":
        print("%d problem(s). Fix them and run validate-overview again." % len(errors) if errors
              else "The overview file is not written yet.")
        sys.exit(1)


def cmd_status(module, only_next=False):
    """The state of every work item, and the next step for a person who runs the steps by hand."""
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
    print("\nNext: %s (%s). %s\nOpen a new Copilot agent chat and paste this line:\n" % (w["id"], state, STEP[state][1]))
    print("  " + item_task(module, w["id"], state))


def cmd_selfcheck():
    """Checks the installation: Python, the parser library, config.json and the module folders."""
    ok = True

    def report(good, text):
        nonlocal ok
        ok = ok and good
        print(("[ OK ] " if good else "[FAIL] ") + text)

    report(sys.version_info >= (3, 7), "Python %s (3.7 or newer is needed)" % sys.version.split()[0])
    report(True, "Java parser library loads from the vendor folder")
    try:
        cfg = load_config()
        report(os.path.isdir(cfg["source_root"]), "source_root exists: %s" % cfg["source_root"])
        for name in cfg["modules"]:
            for path in module_dirs(cfg, name):
                n = sum(bool(java_index.file_type(f, cfg.get("file_types")))
                        for _d, _s, fs in os.walk(path) for f in fs)
                report(n > 0, "module %s: %d Java, SQL and configuration files in %s" % (name, n, path))
        print("[ OK ] execution check: Java compiler found" if run_check.tools(cfg) else
              "[INFO] execution check: switched off or no Java compiler (javac). Examples will not be run against the code.")
        inside = not os.path.relpath(HERE, cfg["source_root"]).startswith("..")
        report(inside, "pipeline folder is inside source_root, so the Copilot agent can read both")
    except Exception as exc:
        report(False, "config.json cannot be read: %s" % exc)
    print("\nAll checks passed." if ok else "\nFix the FAIL lines before you continue.")
    sys.exit(0 if ok else 1)


# commands that read their own options
WITH_OPTIONS = {"run": cmd_run, "prepare": cmd_prepare, "calibrate": cmd_calibrate}
# commands that take exactly one name: a module, or a work item for 'validate'
WITH_ONE_NAME = {
    "step": cmd_step,
    "next": lambda module: cmd_status(module, only_next=True),
    "status": cmd_status,
    "validate": cmd_validate,
    "validate-overview": cmd_validate_overview,
    "coverage": cmd_coverage,
    "build-doc": cmd_build_doc,
}


def main(usage):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    names = [a for a in sys.argv[1:] if not a.startswith("--")]
    flags = {a for a in sys.argv[1:] if a.startswith("--")}
    if not names:
        sys.exit(usage)
    command, rest = names[0], names[1:]
    if command == "selfcheck":
        cmd_selfcheck()
    elif command in WITH_OPTIONS:
        WITH_OPTIONS[command](sys.argv[2:])
    elif len(rest) != 1:
        sys.exit(usage)
    elif command == "inventory":
        cmd_inventory(rest[0], force="--force" in flags)
    elif command in WITH_ONE_NAME:
        WITH_ONE_NAME[command](rest[0])
    else:
        sys.exit(usage)
