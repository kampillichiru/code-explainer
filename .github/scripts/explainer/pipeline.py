"""prepare and step: the run driven from Copilot Chat.

'prepare' registers the module and builds the work items. The chat then repeats 'step': Python names
the next task, the chat starts the agent for it. Python never calls a model here, and the chat never
decides what comes next.
"""

import argparse
import os
import re
import sys
import time

from .coverage import cmd_coverage
from .document import cmd_build_doc
from .inventory import cmd_inventory
from .notes import NOTES_ABOUT, NOTES_TERMS, module_domain, module_notes, notes_section, write_module_notes
from .state import item_state, overview_state
from .store import (
    HERE,
    json_files,
    load_config,
    module_dirs,
    out_dir,
    output_fingerprint,
    prompt_hash,
    read_json,
    read_text_file,
    snapshot,
    work_items,
    write_json,
)
from .tasks import item_task, notes_hint, overview_task, step_file, step_name

# Defaults for the "runner" block of config.json.
RUNNER = {
    "command": ["claude", "-p", "--model", "{model}", "--permission-mode", "acceptEdits",
                "--allowedTools", "Read,Glob,Grep,Write,Edit"],
    "models": {"extract": "sonnet", "verify": "opus", "resolve": "opus", "recheck": "sonnet", "overview": "opus",
               "calibrate": "opus"},
    "parallel": 3,
    "max_calls_per_item": 6,
    "timeout_minutes": 30,
    # a call that fails and writes nothing (usage limit, login, network) is not an attempt at the work item:
    # it is tried again after a wait, and this many in a row stop the whole run
    "runner_failures_before_stop": 3,
    "retry_wait_seconds": 30,
}


def runner_settings(cfg):
    return dict(RUNNER, **cfg.get("runner", {}))


def utc_now(seconds=None):
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(seconds))


def changed_files(before, now):
    return sorted(f for f in set(before) | set(now) if before.get(f) != now.get(f))


def add_run_record(module, key, record):
    """runs/<key>.json keeps one record for every step that was started: what ran, when, on which sources."""
    path = out_dir(module, "runs", key + ".json")
    records = read_json(path) if os.path.isfile(path) else []
    records.append(record)
    write_json(path, records)


# ---------------------------------------------------------------- prepare

def prepare(command, argv):
    """Shared start of 'run' and 'prepare': registers the module, saves the notes, builds the inventory."""
    ap = argparse.ArgumentParser(prog="explain.py " + command)
    ap.add_argument("module")
    ap.add_argument("--path", nargs="+", help="module folder or folders (Java, SQL, configuration), "
                                              "relative to source_root (adds them to config.json)")
    ap.add_argument("--domain", help="business domain of the module, for example \"Accounts receivable\", "
                                     "\"Payments\" or \"Order management\" (needed the first time)")
    ap.add_argument("--about", help="what the business team knows about this module")
    ap.add_argument("--about-file", help="the same, read from a text file")
    ap.add_argument("--terms-file", help="text file with the business terms, their meaning, and the users and roles")
    ap.add_argument("--parallel", type=int)
    opts = ap.parse_args(argv)
    module = opts.module

    if opts.path:
        register_folders(module, opts.path)
    cfg = load_config()
    if module not in cfg["modules"]:
        sys.exit("Module '%s' is not listed in config.json. Give its folder with --path." % module)
    notes = save_notes(module, opts)
    if not work_items(module):
        cmd_inventory(module)
    return opts, cfg, notes


def register_folders(module, folders):
    cfg_path = os.path.join(HERE, "config.json")
    raw = read_json(cfg_path)
    paths = [p.replace("\\", "/") for p in folders]
    raw.setdefault("modules", {})[module] = paths[0] if len(paths) == 1 else paths
    write_json(cfg_path, raw)


def save_notes(module, opts):
    """Writes module-info.md from the options, keeping what an earlier run saved. Returns its text."""
    old = module_notes(module)
    old_domain = module_domain(module)
    domain = " ".join((opts.domain or old_domain).split())
    if not domain:
        sys.exit("Give the business domain of module '%s' with --domain, for example: --domain \"Order management\".\n"
                 "The agents take their business terms from it. It is never guessed from the code." % module)
    if old_domain and domain != old_domain and json_files(out_dir(module, "rules")):
        print("WARNING: the domain changes from '%s' to '%s', but some work items were already written with the "
              "old one. To write them again, run: python explain.py inventory %s --force" % (old_domain, domain, module))
    # notes saved by an older version have no headings: the whole text is what the business team said
    old_about = notes_section(old, NOTES_ABOUT) if re.search(r"^## ", old, re.M) else old.strip()
    about = (read_text_file(opts.about_file) if opts.about_file else opts.about) or old_about
    terms = read_text_file(opts.terms_file) if opts.terms_file else notes_section(old, NOTES_TERMS)
    return write_module_notes(module, domain, about, terms)


def cmd_prepare(argv):
    opts, cfg, _notes = prepare("prepare", argv)
    module = opts.module
    write_json(out_dir(module, "source-hashes.json"), snapshot(module_dirs(cfg, module), cfg["source_root"]))
    write_json(out_dir(module, "attempts.json"), {})
    print("PREPARED: %s, %d work items. Now repeat: python explain.py step %s" % (module, len(work_items(module)), module))


# ---------------------------------------------------------------- step

class Attempts:
    """attempts.json: how often each task was given out, so that a task that keeps failing is given up.

    Python cannot see an agent fail in chat mode. It sees it one step later: the files the agent should
    have written are unchanged. Such a call (a usage limit, a tool failure) is taken off the count again.
    """

    def __init__(self, module):
        self.module = module
        self.path = out_dir(module, "attempts.json")
        self.counts = read_json(self.path)
        self.last = self.counts.pop("_last", None)
        self.empty = self.counts.pop("_empty", 0)
        if self.last and output_fingerprint(module, self.last["key"]) == self.last["fingerprint"]:
            # the agent wrote nothing: a usage limit or a tool failure, not an attempt at the work item
            self.counts[self.last["key"]] = max(0, self.counts.get(self.last["key"], 1) - 1)
            self.empty += 1
        else:
            self.empty = 0
        write_json(self.path, self.counts)

    def of(self, key):
        return self.counts.get(key, 0)

    def issued(self, key):
        """A task for 'key' is given out now."""
        self.counts[key] = self.counts.get(key, 0) + 1
        self.counts["_last"] = {"key": key, "fingerprint": output_fingerprint(self.module, key)}
        self.counts["_empty"] = self.empty
        write_json(self.path, self.counts)


def cmd_step(module):
    """Prints the next task for the chat agent, or FINISHED. The chat repeats this until FINISHED."""
    cfg = load_config()
    base_path = out_dir(module, "source-hashes.json")
    if not os.path.isfile(base_path):
        sys.exit("Run first: python explain.py prepare %s" % module)
    before = read_json(base_path)
    changed = changed_files(before, snapshot(module_dirs(cfg, module), cfg["source_root"]))
    if changed:
        print("STOP: source files changed since prepare. Restore them, then run prepare again.")
        for f in changed:
            print("  " + f)
        sys.exit(1)
    if not module_domain(module):
        sys.exit("No business domain is saved for %s. Run prepare again with --domain." % module)

    runner = runner_settings(cfg)
    limit = runner["max_calls_per_item"]
    attempts = Attempts(module)
    if attempts.empty >= runner["runner_failures_before_stop"]:
        print("STOP: the last %d agent calls wrote nothing (last one: %s). This is a usage limit or a tool "
              "failure, not a problem with the code. No attempt was counted. Fix it, then run step again."
              % (attempts.empty, attempts.last["key"]))
        sys.exit(1)

    chosen, stuck, left = None, [], 0
    for w in work_items(module):
        state, _errors = item_state(w)
        if state == "DONE":
            continue
        if attempts.of(w["id"]) >= limit:
            stuck.append((w["id"], state))
            continue
        left += 1
        chosen = chosen or (w, state)

    if chosen is not None:
        give_item_task(module, chosen[0], chosen[1], attempts, before, left)
        return
    # every flow is done or stuck: the module overview is the last task
    key, (ostate, _errors) = module + "-overview", overview_state(module)
    if ostate.startswith("OVERVIEW") and attempts.of(key) >= limit:
        stuck.append((key, ostate))
    elif ostate.startswith("OVERVIEW"):
        give_overview_task(module, key, ostate, attempts)
        return
    cmd_coverage(module)
    cmd_build_doc(module)
    for item_id, state in stuck:
        print("STUCK: %s stopped at %s after %d attempts." % (item_id, state, limit))
    print("FINISHED")


def give_item_task(module, w, state, attempts, source_hashes, left):
    step = step_name(state)
    attempts.issued(w["id"])
    add_run_record(module, w["id"], {
        "step": step, "runner": "copilot-chat", "agent": "explainer-" + step,
        "started_utc": utc_now(),
        "prompt_sha256": prompt_hash(step_file(state)),
        "source_sha256": {f: source_hashes.get(f) for f in
                          sorted({m["file"] for m in w["methods_to_document"] + w["context_methods"]})},
        "state_before": state,
    })
    task = item_task(module, w["id"], state)
    if state.endswith("_INVALID"):
        task += " The file from the last attempt failed validation: run `python explain.py validate %s`, " \
                "fix those problems in the file and keep what is right." % w["id"]
    print("REMAINING: %d work items" % left)
    print("AGENT: explainer-%s" % step)
    print("TASK: " + task + notes_hint(module))


def give_overview_task(module, key, state, attempts):
    attempts.issued(key)
    add_run_record(module, key, {
        "step": "overview", "runner": "copilot-chat", "agent": "explainer-overview",
        "started_utc": utc_now(),
        "prompt_sha256": prompt_hash("overview.md"), "state_before": state,
    })
    task = overview_task(module)
    if state == "OVERVIEW_INVALID":
        task += " The file from the last attempt failed validation: run `python explain.py " \
                "validate-overview %s`, fix those problems in the file and keep what is right." % module
    print("REMAINING: module overview")
    print("AGENT: explainer-overview")
    print("TASK: " + task + notes_hint(module))
