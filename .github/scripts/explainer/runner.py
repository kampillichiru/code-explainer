"""run: the whole pipeline from the terminal, with no person in the loop.

Python calls the model command of config.json for every step, several work items in parallel, checks
each result, and decides the next step from the state of the files.
"""

import os
import shutil
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from . import run_check
from .coverage import cmd_coverage
from .document import cmd_build_doc
from .pipeline import RUNNER, add_run_record, changed_files, prepare, runner_settings, utc_now
from .state import item_state, overview_state
from .store import HERE, module_dirs, out_dir, output_fingerprint, plain, prompt_hash, shown, snapshot, work_items
from .tasks import item_task, overview_task, step_file, step_name


class Run:
    """One run of a module. Shared by the worker threads: what they print and the stop signal go through here."""

    def __init__(self, module, cfg, notes):
        self.module, self.cfg, self.notes = module, cfg, notes
        self.runner = runner_settings(cfg)
        self.models = dict(RUNNER["models"], **self.runner.get("models", {}))
        self.exe = shutil.which(self.runner["command"][0])
        if not self.exe:
            sys.exit("Command not found: %s. Set runner.command in config.json." % self.runner["command"][0])
        self.root = plain(cfg["source_root"])
        # a pipeline folder outside the source root has to be opened to the model command
        self.extra = [] if not os.path.relpath(HERE, cfg["source_root"]).startswith("..") else ["--add-dir", plain(HERE)]
        self.dirs = module_dirs(cfg, module)
        self.before = snapshot(self.dirs, cfg["source_root"])  # the sources must not change during the run
        self.lock, self.stop, self.halted = threading.Lock(), threading.Event(), []

    def say(self, text):
        with self.lock:
            print(text, flush=True)

    def prompt_for(self, first_line, errors):
        lines = [first_line, "",
                 "You are running with no human present. Do not ask questions; decide and write the file.",
                 "Do not run explain.py. The runner validates your file after you finish."]
        lines += ["", "The business domain of this module and what the business team says about it. Use it for "
                      "names and meaning. If the code does something different, the code wins and you add a "
                      "question for the SME:", self.notes.strip()]
        if errors:
            lines += ["", "The file from the last attempt exists and failed validation. "
                          "Fix these problems in it and keep what is right:"]
            lines += ["- " + e for e in errors]
        return "\n".join(lines)

    def call(self, key, step, prompt, log):
        """One model call. Returns the facts for the run record, and the source files it changed."""
        runner = self.runner
        wrote_before = output_fingerprint(self.module, key)
        os.makedirs(os.path.dirname(log), exist_ok=True)
        args = runner["command"][1:]
        # a tool that takes its prompt as an argument gets a one-line pointer to a prompt file instead of stdin
        if any("{prompt_file}" in a for a in args):
            prompt_file = log[:-4] + ".prompt.md"
            with open(prompt_file, "w", encoding="utf-8") as fh:
                fh.write(prompt)
            args = [a.replace("{prompt_file}", shown(prompt_file)) for a in args]
            feed = None
        else:
            feed = prompt
        cmd = [self.exe] + [a.replace("{model}", self.models[step]) for a in args] + self.extra
        started = time.time()
        # the model command is often a launcher that starts the real program: a timeout stops the whole tree
        exit_code, said, complained = run_check.run_limited(cmd, self.root, runner["timeout_minutes"] * 60, feed)
        if exit_code is None:
            text = "timed out after %g minutes and was stopped\n\n%s\n%s" % (runner["timeout_minutes"], said, complained)
        else:
            text = "exit code %d\n\n%s\n%s" % (exit_code, said, complained)
        with open(log, "w", encoding="utf-8") as fh:
            fh.write(text)
        changed = changed_files(self.before, snapshot(self.dirs, self.cfg["source_root"]))
        if changed:
            self.stop.set()
        record = {"step": step, "model": self.models[step], "command": runner["command"],
                  "started_utc": utc_now(started),
                  "seconds": round(time.time() - started, 1), "exit_code": exit_code,
                  "source_files_changed": changed}
        if exit_code not in (0, None) and output_fingerprint(self.module, key) == wrote_before:
            # the command failed and wrote nothing: usage limit, login, network. Not an attempt at the work item.
            said = [line.strip() for line in text.splitlines()[1:] if line.strip()]
            record["runner_failed"] = (said[-1] if said else "exit code %d, no output" % exit_code)[:300]
        return record, changed

    def must_halt(self, key, record, failures):
        """True when the run must stop: the command failed several times in a row without writing anything."""
        runner = self.runner
        if failures >= runner["runner_failures_before_stop"]:
            with self.lock:
                self.halted.append("%s: %s" % (key, record["runner_failed"]))
            self.stop.set()
            return True
        self.say("%s: the model command failed and wrote nothing (%s). Not counted as an attempt. Waiting %d seconds."
                 % (key, record["runner_failed"], runner["retry_wait_seconds"] * failures))
        self.stop.wait(runner["retry_wait_seconds"] * failures)
        return False

    def work_until_done(self, key, state_of, open_, plan, source_files=None, restore_note=""):
        """Repeats 'next step, call the model, check the result' for one work item, or for the overview.

        state_of() gives (state, errors). open_(state) says if work is left. plan(state) gives the step
        name, its instruction file and the task line. Returns (key, last state, calls that counted).
        """
        calls = failures = tries = 0
        state, errors = state_of()
        while open_(state) and calls < self.runner["max_calls_per_item"] and not self.stop.is_set():
            step, instructions, task = plan(state)
            calls += 1
            tries += 1
            self.say("%s: %s -> %s (%s, call %d)" % (key, state, step, self.models[step], calls))
            record, changed = self.call(key, step, self.prompt_for(task, errors),
                                        out_dir(self.module, "logs", "%s-%d-%s.txt" % (key, tries, step)))
            new_state, errors = state_of()
            record["prompt_sha256"] = prompt_hash(instructions)
            if source_files is not None:
                record["source_sha256"] = {f: self.before.get(f) for f in source_files}
            record.update(state_before=state, state_after=new_state)
            add_run_record(self.module, key, record)
            if changed:
                self.say("%s: STOPPED. Source files changed during this call:\n  %s%s"
                         % (key, "\n  ".join(changed), restore_note))
                return key, "SOURCE_CHANGED", calls
            state = new_state
            if "runner_failed" not in record:
                failures = 0
                continue
            calls -= 1
            failures += 1
            if self.must_halt(key, record, failures):
                break
        return key, state, calls

    def run_item(self, w):
        return self.work_until_done(
            w["id"],
            state_of=lambda: item_state(w),
            open_=lambda state: state != "DONE",
            plan=lambda state: (step_name(state), step_file(state), item_task(self.module, w["id"], state)),
            source_files=sorted({m["file"] for m in w["methods_to_document"] + w["context_methods"]}),
            restore_note="\nRestore them, then run again. No further model calls will start.")

    def run_overview(self):
        """The last task: why the module exists and its types of flow, written from the documented flows."""
        key, state, calls = self.work_until_done(
            self.module + "-overview",
            state_of=lambda: overview_state(self.module),
            open_=lambda state: state.startswith("OVERVIEW"),
            plan=lambda state: ("overview", "overview.md", overview_task(self.module)))
        return key, ("DONE" if state == "NONE" else state), calls


def cmd_run(argv):
    opts, cfg, notes = prepare("run", argv)
    module = opts.module
    run = Run(module, cfg, notes)
    items = work_items(module)

    with ThreadPoolExecutor(opts.parallel or run.runner["parallel"]) as pool:
        try:
            results = list(pool.map(run.run_item, items))
        except KeyboardInterrupt:  # Ctrl+C: stop the model calls that are running, start no new ones
            run.stop.set()
            run_check.stop_all()
            raise
    overview = run.run_overview()

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
    if run.halted:
        print("\nRUN HALTED: the model command failed %d times in a row without writing anything. This is a usage "
              "limit, a login or a network problem, not a problem with the code. These calls were not counted as "
              "attempts.\n  %s\nFix it and run the same command again: finished work is kept."
              % (run.runner["runner_failures_before_stop"], "\n  ".join(run.halted)))
    sys.exit(1 if stuck else 0)
