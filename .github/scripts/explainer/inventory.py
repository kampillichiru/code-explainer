"""Inventory: cuts one module into work items. No AI is used.

A work item is one flow: an entry point and the code it reaches. It names the code to read and carries
the checklist of everything in that code that must be explained.
"""

import os
import sys

from . import java_index, run_check
from .coverage import execution_line, unread_files
from .store import json_files, load_config, module_dirs, out_dir, plain, shown, write_json

ITEM_KINDS = ["if", "case", "ternary", "catch", "loop", "calc", "constant", "sql", "method", "config"]


def cmd_inventory(module, force=False):
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
    for old in json_files(out_dir(module, "exec")):  # results of runs for the work items of the last inventory
        os.remove(old)
    runnable = run_check.prepare(index, cfg, cfg["source_root"], out_dir(module, "exec"))

    groups = join_small_flows(find_flows(methods), methods, cfg.get("target_lines", 400))
    parts = split_large_flows(groups, methods, cfg.get("max_lines", 1200))

    for old in json_files(out_dir(module, "work")):
        os.remove(old)
    total_items = 0
    for n, part in enumerate(parts, 1):
        item = work_item(module, "%s-%03d" % (module, n), part, methods, runnable, cfg)
        total_items += len(item["items_to_cover"])
        write_json(out_dir(module, "work", item["id"] + ".json"), item)

    failed = {f: v["error"] for f, v in index["files"].items() if not v["parsed"]}
    write_json(out_dir(module, "inventory.json"), {
        "module": module, "files": len(index["files"]), "methods": len(methods),
        "trivial_methods": sum(1 for m in methods.values() if m["trivial"]),
        "work_items": len(parts), "items_to_cover": total_items,
        "files_not_parsed": failed, "runnable_methods": len(runnable),
    })
    print("Module %s: %d files, %d methods, %d work items, %d items to cover."
          % (module, len(index["files"]), len(methods), len(parts), total_items))
    if failed:
        print("%d file(s) could not be parsed. Each is one work item for the whole file:" % len(failed))
        for f, err in failed.items():
            print("  %s  (%s)" % (f, err))
    print(execution_line(module))
    unread = unread_files(module)
    if unread:
        print("NOT READ: %d file(s) in the module folders are of a type this tool does not read: %s. "
              "See the coverage report." % (sum(map(len, unread.values())),
                                            ", ".join("%s (%d)" % (e, len(unread[e])) for e in sorted(unread))))


def reachable(methods, start):
    """The method and everything it calls inside the module, in the order the code is read."""
    seen, order, todo = set(), [], [start]
    while todo:
        mid = todo.pop()
        if mid in seen:
            continue
        seen.add(mid)
        order.append(mid)
        todo.extend(reversed(methods[mid]["callees"]))
    return order


def find_flows(methods):
    """One unit for each entry point (code that nothing in the module calls), with the code only it reaches."""
    callers = {mid: set() for mid in methods}
    for mid, m in methods.items():
        for c in m["callees"]:
            callers[c].add(mid)

    # Java first: a stored procedure that Java calls then belongs to the Java flow that calls it
    ordered = sorted(methods.values(), key=lambda m: (not m["file"].endswith(".java"), m["file"], m["start"]))
    entries = [m["id"] for m in ordered if not callers[m["id"]] and not m["private"]]
    owner, units = {}, []
    for entry in entries:
        owned = [mid for mid in reachable(methods, entry) if mid not in owner]
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
    return units


def lines_of(methods, mids):
    return sum(methods[x]["end"] - methods[x]["start"] + 1 for x in mids)


def join_small_flows(units, methods, target):
    """Small flows of the same file and kind share one work item, up to 'target' lines of code."""
    groups = []
    for u in units:
        last = groups[-1] if groups else None
        same_file = last and methods[last["entries"][0]]["file"] == methods[u["entries"][0]]["file"]
        if same_file and last["kind"] == u["kind"] and lines_of(methods, last["methods"] + u["methods"]) <= target:
            last["entries"] += u["entries"]
            last["methods"] += u["methods"]
        else:
            groups.append(u)
    return groups


def split_large_flows(groups, methods, limit):
    """A flow with more than 'limit' lines of code becomes several work items, cut between methods."""
    parts = []
    for g in groups:
        chunk = []
        for mid in g["methods"]:
            if chunk and lines_of(methods, chunk + [mid]) > limit:
                parts.append(dict(g, methods=chunk))
                chunk = []
            chunk.append(mid)
        parts.append(dict(g, methods=chunk))
    return parts


def work_item(module, item_id, part, methods, runnable, cfg):
    """The work item as the agents read it: the code to explain, the code around it, and the checklist."""

    def brief(mid):
        m = methods[mid]
        return {"method": mid.split("#", 1)[1].rsplit(":", 1)[0], "file": m["file"],
                "start_line": m["start"], "end_line": m["end"]}

    own = set(part["methods"])
    context, external = [], set()
    for mid in part["methods"]:
        external.update(methods[mid]["external"])
        for c in methods[mid]["callees"] + methods[mid]["reads"]:
            if c not in own and c not in context and not methods[c]["trivial"]:
                context.append(c)
    return {
        "id": item_id, "module": module, "kind": part["kind"],
        "source_root": plain(cfg["source_root"]).replace("\\", "/"),
        "entry_points": [brief(e) for e in part["entries"]],
        "methods_to_document": [brief(mid) for mid in part["methods"]],
        "context_methods": [brief(c) for c in context],
        "calls_to_other_modules": sorted(external),
        "items_to_cover": [i for mid in part["methods"] for i in methods[mid]["items"]],
        "runnable_methods": [runnable[mid] for mid in part["methods"] if mid in runnable],
        "rules_file": shown(out_dir(module, "rules", item_id + ".json")),
        "verify_file": shown(out_dir(module, "verify", item_id + ".json")),
    }
