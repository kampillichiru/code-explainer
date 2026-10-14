"""Execution check: runs the real code with the inputs of an example and compares the result.

No AI is used here. A method is run only when reading it shows that it is safe to run on its own:
it takes and returns plain values (numbers, text, dates), and neither it nor anything it calls touches a
database, a file, the network, the clock or code outside the module. Everything is compiled into the output
folder, never into the source folders.
"""
import hashlib
import json
import os
import re
import shutil
import signal
import subprocess
import threading
from decimal import Decimal, InvalidOperation

HARNESS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ExplainerHarness.java")
DEFAULTS = {"enabled": True, "javac": "javac", "java": "java", "classpath": [], "encoding": "", "timeout_seconds": 20}

WHOLE = {"int", "long", "short", "byte", "Integer", "Long", "Short", "Byte", "BigInteger"}
FLOATING = {"double", "float", "Double", "Float"}
PRIMITIVE = {"int", "long", "short", "byte", "double", "float", "boolean", "char"}
DATES = {"Date", "Timestamp"}
TYPES = WHOLE | FLOATING | DATES | {"BigDecimal", "boolean", "Boolean", "char", "Character", "String"}

# what a method may use and still be run: arithmetic, text and comparison, nothing that reaches outside
PURE_TYPES = {"Math", "StrictMath", "BigDecimal", "BigInteger", "String", "Integer", "Long", "Double", "Float", "Short",
              "Byte", "Boolean", "Character", "StringBuilder", "StringBuffer", "Date", "Timestamp", "MathContext",
              "RoundingMode", "Number"}
PURE_NEW = {"BigDecimal", "BigInteger", "String", "StringBuilder", "StringBuffer", "Integer", "Long", "Double", "Float",
            "Short", "Byte", "Boolean", "Character", "MathContext"}
LOG_TYPES = {"Logger", "Log", "LogManager", "LogFactory", "LoggerFactory"}
SAFE_NAMES = set(
    "add subtract multiply divide remainder pow negate abs signum setScale scale precision round floor ceil rint sqrt "
    "max min compareTo compare equals equalsIgnoreCase hashCode intValue longValue doubleValue floatValue shortValue "
    "byteValue booleanValue intValueExact longValueExact valueOf parseInt parseLong parseDouble parseFloat parseBoolean "
    "toString toPlainString stripTrailingZeros movePointLeft movePointRight length isEmpty trim charAt substring "
    "indexOf lastIndexOf contains startsWith endsWith toUpperCase toLowerCase replace concat append insert reverse "
    "matches getTime before after isNaN isInfinite".split()
)
PRINTS = {"print", "println", "printf"}


def settings(cfg):
    return dict(DEFAULTS, **(cfg.get("execution") or {}))


def tools(cfg):
    """Paths of the Java compiler and of the Java launcher, or None when the check cannot run here."""
    conf = settings(cfg)
    if not conf["enabled"]:
        return None
    javac, java = shutil.which(conf["javac"]), shutil.which(conf["java"])
    return (javac, java) if javac and java else None


def _plain(path):
    return path[4:] if path.startswith("\\\\?\\") else path


def _sha(*texts):
    h = hashlib.sha256()
    for t in texts:
        h.update(t if isinstance(t, bytes) else str(t).encode("utf-8"))
    return h.hexdigest()


# ---------------------------------------------------------------- which methods can be run

def signature(m):
    return "%s(%s)" % (m["id"].split("#", 1)[1].rsplit(":", 1)[0], ", ".join(t for _n, t in m["params"]))


def find_runnable(index):
    """Methods that reading the code shows to be safe to run on their own: {method id: spec}. Not compiled yet."""
    classes, methods = index["classes"], index["methods"]
    by_simple = {}
    for fqn, c in classes.items():
        by_simple.setdefault(c["simple"], []).append(fqn)
    class_memo, method_memo = {}, {}

    def module_class(simple):
        found = by_simple.get(simple, [])
        return found[0] if len(found) == 1 else None

    def class_ok(fqn):
        """Loading the class and creating an object of it starts no other work."""
        if fqn not in class_memo:
            class_memo[fqn] = True  # a class that refers to itself
            c = classes[fqn]
            ok = c.get("plain_class") and not c["extends"] and not c["init_blocks"]
            ok = ok and all(q.split(".")[0] in LOG_TYPES for q, _name in c["field_calls"])
            for t in c["field_news"] if ok else []:
                other = module_class(t)
                ok = ok and (t in PURE_NEW or bool(other and class_ok(other) and not classes[other]["constructors"]))
            class_memo[fqn] = bool(ok)
        return class_memo[fqn]

    def creatable(simple):
        fqn = module_class(simple)
        return bool(fqn and class_ok(fqn) and not classes[fqn]["constructors"])

    def call_ok(m, qual, name, callee_names):
        if qual in ("System.out", "System.err"):
            return name in PRINTS
        if qual == "<chained>":
            return name in SAFE_NAMES or name in callee_names
        if qual in ("", "this", "super"):
            return name in callee_names
        q = qual[5:] if qual.startswith("this.") else qual
        first = q.split(".")[0]
        if "." in q:  # a value inside another object: only plain arithmetic and text on it
            return name in SAFE_NAMES
        kind = m["vars"].get(first) or classes[m["cls"]]["fields"].get(first) or (first if first[:1].isupper() else None)
        if kind in LOG_TYPES:
            return True
        if kind in PURE_TYPES:
            return name in SAFE_NAMES
        return bool(kind and module_class(kind)) and name in callee_names

    def method_ok(mid):
        if mid not in method_memo:
            method_memo[mid] = True  # a method that calls itself
            m = methods[mid]
            ok = bool(m.get("cls")) and "params" in m and m["has_body"] and not m["abstract"] and not m["constructor"]
            ok = ok and class_ok(m["cls"]) and (m["static"] or not classes[m["cls"]]["constructors"])
            ok = ok and not m["external"] and not any(i["kind"] == "sql" for i in m["items"])
            ok = ok and all(t in PURE_NEW or t.endswith(("Exception", "Error")) or creatable(t) for t in m["news"])
            if ok:
                names = {methods[c]["name"] for c in m["callees"]}
                ok = all(call_ok(m, q, n, names) for q, n, _args in m["calls"]) and all(method_ok(c) for c in m["callees"])
            method_memo[mid] = bool(ok)
        return method_memo[mid]

    found = {}
    for mid, m in methods.items():
        if not m.get("cls") or "params" not in m or m["trivial"] or not m["items"]:
            continue
        if m["returns"] not in TYPES or any(t not in TYPES for _n, t in m["params"]):
            continue
        if method_ok(mid):
            found[mid] = {
                "method": signature(m), "class": m["cls"], "name": m["name"], "static": m["static"],
                "params": [{"name": n, "type": t} for n, t in m["params"]], "returns": m["returns"], "file": m["file"],
            }
    return found


def source_roots(index, source_root):
    """Folders a Java compiler needs to find the classes of the module, relative to source_root."""
    roots = set()
    for c in index["classes"].values():
        folder = os.path.dirname(c["file"])
        package = c["package"].replace(".", "/")
        if package and (folder == package or folder.endswith("/" + package)):
            folder = folder[:len(folder) - len(package)].rstrip("/")
        roots.add(folder or ".")
    return sorted(roots)


def compile_files(cfg, source_root, roots, files, build):
    """Compiles the harness and the given source files into 'build'. Returns '' or the compiler's complaint."""
    conf, found = settings(cfg), tools(cfg)
    if not found:
        return "no Java compiler"
    shutil.rmtree(build, ignore_errors=True)
    os.makedirs(build)
    src = _plain(source_root)
    cmd = [found[0], "-nowarn", "-proc:none", "-implicit:class", "-d", _plain(build),
           "-sourcepath", os.pathsep.join(os.path.normpath(os.path.join(src, r)) for r in roots)]
    if conf["classpath"]:
        cmd += ["-cp", os.pathsep.join(conf["classpath"])]
    if conf["encoding"]:
        cmd += ["-encoding", conf["encoding"]]
    cmd += [HARNESS] + [os.path.normpath(os.path.join(src, f)) for f in sorted(set(files))]
    try:
        done = subprocess.run(cmd, capture_output=True, encoding="utf-8", errors="replace", timeout=600)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return "compiler did not finish: %s" % exc
    if done.returncode:
        lines = [x.strip() for x in (done.stderr or done.stdout).splitlines() if x.strip()]
        return (lines[0] if lines else "compiler failed")[:300]
    return ""


def prepare(index, cfg, source_root, exec_dir):
    """At inventory time: finds the runnable methods, keeps those that compile, saves the setup.

    Returns {method id: spec}. An empty result is normal: legacy code often cannot be compiled without its libraries.
    """
    setup = {"available": False, "reason": "", "source_roots": [], "runnable_methods": 0, "does_not_compile": {}}
    specs = {}
    if not settings(cfg)["enabled"]:
        setup["reason"] = "Switched off in config.json (execution.enabled)."
    elif not tools(cfg):
        setup["reason"] = "No Java compiler (javac) was found on this machine."
    else:
        specs = find_runnable(index)
        roots = source_roots(index, source_root)
        setup.update(available=True, source_roots=roots)
        files = sorted({s["file"] for s in specs.values()})
        probe = os.path.join(exec_dir, "build", "_probe")
        if files and compile_files(cfg, source_root, roots, files, probe):
            for f in files:  # find the files that do not compile on their own, and leave only those out
                problem = compile_files(cfg, source_root, roots, [f], probe)
                if problem:
                    setup["does_not_compile"][f] = problem
            specs = {mid: s for mid, s in specs.items() if s["file"] not in setup["does_not_compile"]}
        shutil.rmtree(probe, ignore_errors=True)
        setup["runnable_methods"] = len(specs)
    os.makedirs(exec_dir, exist_ok=True)
    with open(os.path.join(exec_dir, "setup.json"), "w", encoding="utf-8") as fh:
        json.dump(setup, fh, indent=2)
    return specs


# ---------------------------------------------------------------- values in and out

DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})(?:[ T](\d{2}:\d{2}:\d{2}))?$")


def encode_arg(kind, value):
    """The argument as the harness reads it, or raises ValueError with the reason."""
    if value is None:
        if kind in PRIMITIVE:
            raise ValueError("a value is needed")
        return "\\N"
    if kind in ("boolean", "Boolean"):
        if isinstance(value, bool) or str(value).lower() in ("true", "false"):
            return str(value).lower()
        raise ValueError("must be true or false")
    if isinstance(value, bool):
        raise ValueError("must not be true or false")
    text = str(value).strip() if kind != "String" else str(value)
    if kind in WHOLE:
        text = text.rstrip("Ll")
        if not re.fullmatch(r"-?\d+", text):
            raise ValueError("must be a whole number, without separators")
    elif kind in FLOATING or kind == "BigDecimal":
        if not re.fullmatch(r"-?\d+(\.\d+)?", text):
            raise ValueError("must be a plain number such as 10000.00, without separators or a unit")
    elif kind in DATES:
        found = DATE_RE.match(text)
        if not found:
            raise ValueError("must be a date as YYYY-MM-DD or YYYY-MM-DD HH:MM:SS")
        text = "%s %s" % (found.group(1), found.group(2) or "00:00:00")
    elif kind in ("char", "Character"):
        if len(text) != 1:
            raise ValueError("must be one character")
    return text.replace("\\", "\\\\").replace("\t", "\\t").replace("\n", "\\n").replace("\r", "\\r")


def _unescape(text):
    return re.sub(r"\\(.)", lambda m: {"t": "\t", "n": "\n", "r": "\r"}.get(m.group(1), m.group(1)), text)


def same_result(kind, outcome, expected):
    """outcome is what the harness printed: ('VALUE', text), ('NULL',) or ('THROWS', name, message)."""
    said = "" if expected is None else str(expected).lower() if isinstance(expected, bool) else str(expected).strip()
    throws = re.fullmatch(r"throws\s+([\w.]+)", said)
    if outcome[0] == "THROWS":
        return bool(throws) and throws.group(1).split(".")[-1] == outcome[1]
    if throws:
        return False
    if outcome[0] == "NULL":
        return expected is None or said.lower() == "null"
    actual = outcome[1]
    if kind in WHOLE or kind in FLOATING or kind == "BigDecimal":
        try:
            a, e = Decimal(actual), Decimal(said.rstrip("Ll") if kind in WHOLE else said)
        except InvalidOperation:
            return False
        if kind in FLOATING:
            return abs(a - e) <= Decimal("1e-9") * max(Decimal(1), abs(a))
        return a == e
    if kind in ("boolean", "Boolean"):
        return said.lower() == actual.lower()
    if kind in DATES:
        found = DATE_RE.match(said)
        return bool(found) and "%s %s" % (found.group(1), found.group(2) or "00:00:00") == actual
    return said == actual if kind != "String" else ("" if expected is None else str(expected)) == actual


def shown(outcome):
    if outcome[0] == "THROWS":
        return "throws %s%s" % (outcome[1], " (%s)" % outcome[2] if len(outcome) > 2 and outcome[2] != "null" else "")
    return "null" if outcome[0] == "NULL" else outcome[1]


# ---------------------------------------------------------------- run

LIVE = set()  # commands that are running now, so that a Ctrl+C can stop them all
LIVE_LOCK = threading.Lock()


def stop_tree(proc):
    """Stops a command and everything it started. 'java' or a model command on the PATH is often a small
    launcher that starts the real program; stopping only the launcher leaves the real one running."""
    if proc.poll() is not None:
        return
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True)
        else:
            os.killpg(proc.pid, signal.SIGKILL)
    except OSError:
        pass
    if proc.poll() is None:
        proc.kill()


def stop_all():
    with LIVE_LOCK:
        running = list(LIVE)
    for proc in running:
        stop_tree(proc)


def run_limited(cmd, cwd, seconds, text_in=None):
    """Runs a command with a time limit. Returns (exit code, what it printed, its error text).

    The exit code is None when the limit was reached; the whole process tree is then stopped, and what the
    command had printed up to then is still returned.
    """
    own_session = {} if os.name == "nt" else {"start_new_session": True}  # so that killpg reaches the children
    proc = subprocess.Popen(cmd, cwd=cwd, stdin=subprocess.PIPE if text_in is not None else subprocess.DEVNULL,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, encoding="utf-8", errors="replace",
                            **own_session)
    with LIVE_LOCK:
        LIVE.add(proc)
    try:
        try:
            out, err = proc.communicate(text_in, timeout=seconds)
            return proc.returncode, out or "", err or ""
        except subprocess.TimeoutExpired:
            stop_tree(proc)
            try:
                out, err = proc.communicate(timeout=15)
            except (subprocess.TimeoutExpired, ValueError):
                out, err = "", ""
            return None, out or "", err or ""
    finally:
        with LIVE_LOCK:
            LIVE.discard(proc)


def _run_cases(cfg, build, cases):
    """cases: [(id, spec, encoded args)]. Returns {id: outcome tuple}; ('TIMEOUT',) or ('ERROR', text) when it fails."""
    conf, found = settings(cfg), tools(cfg)
    out, left = {}, list(cases)
    classpath = os.pathsep.join([_plain(build)] + list(conf["classpath"]))
    while left:
        spec_path = os.path.join(build, "cases.txt")
        with open(spec_path, "w", encoding="utf-8", newline="\n") as fh:
            for cid, spec, args in left:
                fh.write("CASE\t%s\nCLASS\t%s\nMETHOD\t%s\n" % (cid, spec["class"], spec["name"]))
                for p, a in zip(spec["params"], args):
                    fh.write("ARG\t%s\t%s\n" % (p["type"], a))
                fh.write("RUN\n")
        cmd = [found[1], "-Xmx256m", "-Djava.awt.headless=true", "-cp", classpath, "ExplainerHarness", _plain(spec_path),
               str(conf["timeout_seconds"])]
        try:  # the harness stops a case that runs too long by itself; the limit here is the second line of defence
            code, text, _err = run_limited(cmd, _plain(build), conf["timeout_seconds"] * len(left) + 30)
            timed_out = code is None
        except OSError as exc:
            return dict(out, **{cid: ("ERROR", str(exc)) for cid, _s, _a in left})
        started = None
        for line in text.splitlines():
            f = line.split("\t")
            if f[0] == "START" and len(f) > 1:
                started = f[1]
            elif f[0] == "RESULT" and len(f) > 2:
                out[f[1]] = tuple([f[2]] + [_unescape(x) for x in f[3:]])
        if timed_out and started and started not in out:
            out[started] = ("TIMEOUT",)
        before = len(left)
        left = [c for c in left if c[0] not in out]
        if len(left) == before:  # nothing came back: do not try again
            for cid, _s, _a in left:
                out[cid] = ("TIMEOUT",) if timed_out else ("ERROR", "the run gave no result")
            left = []
    return out


def check(work, data, rule_ids, cfg, source_root, exec_dir, file_hashes):
    """Validates 'code_runs' of a rules file and runs them. Returns the list of error messages.

    The outcome of every run is saved in exec/<work item>.json, for the document.
    """
    specs = {s["method"]: s for s in work.get("runnable_methods") or []}
    runs = data.get("code_runs") or []
    result_path = os.path.join(exec_dir, work["id"] + ".json")
    if not specs:
        if os.path.isfile(result_path):
            os.remove(result_path)
        return ["'code_runs' must be empty: no code of this work item can be run on its own."] if runs else []
    errors, cases, seen, used = [], [], set(), set()
    for n, r in enumerate(runs, 1):
        rid = str(r.get("id", "(code run %d)" % n)) if isinstance(r, dict) else "(code run %d)" % n
        if not isinstance(r, dict) or not re.fullmatch(re.escape(work["id"]) + r"-X\d+", rid):
            errors.append("code_runs %s: id must look like %s-X1." % (rid, work["id"]))
            continue
        if rid in seen:
            errors.append("code_runs %s: id is used twice." % rid)
        seen.add(rid)
        spec = specs.get(r.get("method"))
        if spec is None:
            errors.append("code_runs %s: 'method' must be one of: %s." % (rid, "; ".join(sorted(specs))))
            continue
        used.add(spec["method"])
        if r.get("rule") not in rule_ids:
            errors.append("code_runs %s: 'rule' must be the id of the rule this run is an example of." % rid)
        if "expected" not in r:
            errors.append("code_runs %s: 'expected' is missing: the result you say the code returns." % rid)
        args = r.get("args")
        if not isinstance(args, list) or len(args) != len(spec["params"]):
            errors.append("code_runs %s: 'args' needs %d value(s), in this order: %s."
                          % (rid, len(spec["params"]), ", ".join("%s (%s)" % (p["name"], p["type"]) for p in spec["params"])))
            continue
        encoded = []
        for p, a in zip(spec["params"], args):
            try:
                encoded.append(encode_arg(p["type"], a))
            except ValueError as exc:
                errors.append("code_runs %s: argument '%s' (%s) %s." % (rid, p["name"], p["type"], exc))
        if len(encoded) == len(args):
            cases.append((rid, spec, encoded, r))
    for name in sorted(set(specs) - used):
        errors.append("code_runs: no run for %s. This code can be run on its own, so give at least one example for it." % name)
    if errors:
        return errors

    saved = {"key": None, "runs": {}}
    if not tools(cfg):  # prepared on a machine with Java, checked on one without: say so in the document, do not fail
        saved["runs"] = {c[0]: {"status": "not_run", "note": "No Java compiler on this machine."} for c in cases}
    else:
        key = _sha(json.dumps([[c[0], c[1]["method"], c[2], str(c[3].get("expected"))] for c in cases]),
                   json.dumps(file_hashes, sort_keys=True), open(HARNESS, "rb").read(),
                   json.dumps(settings(cfg), sort_keys=True))
        if os.path.isfile(result_path):
            try:
                with open(result_path, encoding="utf-8") as fh:
                    old = json.load(fh)
                if old.get("key") == key:
                    saved = old
            except ValueError:
                pass
        if saved["key"] != key:
            saved["key"] = key
            setup = json.load(open(os.path.join(exec_dir, "setup.json"), encoding="utf-8"))
            build = os.path.join(exec_dir, "build", work["id"])
            problem = compile_files(cfg, source_root, setup["source_roots"], [c[1]["file"] for c in cases], build)
            outcomes = {} if problem else _run_cases(cfg, build, [c[:3] for c in cases])
            shutil.rmtree(build, ignore_errors=True)
            for rid, spec, _enc, r in cases:
                o = outcomes.get(rid)
                if problem or o is None or o[0] == "ERROR":
                    saved["runs"][rid] = {"status": "not_run", "note": problem or (o[1] if o else "no result")}
                elif o[0] == "TIMEOUT":
                    saved["runs"][rid] = {"status": "timeout"}
                else:
                    ok = same_result(spec["returns"], o, r.get("expected"))
                    saved["runs"][rid] = {"status": "match" if ok else "mismatch", "actual": shown(o)}
    os.makedirs(exec_dir, exist_ok=True)
    with open(result_path, "w", encoding="utf-8") as fh:
        json.dump(saved, fh, indent=2, ensure_ascii=False)

    for rid, _spec, _enc, r in cases:
        got = saved["runs"].get(rid, {})
        if got.get("status") == "mismatch":
            errors.append("code_runs %s: the code was run with these inputs and returns %s, but 'expected' says %s. "
                          "The code is right. Correct 'expected', then make sure that rule %s (its conditions, its "
                          "formula, its rounding and its example) agrees with this result."
                          % (rid, got["actual"], json.dumps(r.get("expected")), r.get("rule")))
        elif got.get("status") == "timeout":
            errors.append("code_runs %s: the code did not finish in %d seconds with these inputs. Use other inputs."
                          % (rid, settings(cfg)["timeout_seconds"]))
    return errors


def results(exec_dir, item_id):
    path = os.path.join(exec_dir, item_id + ".json")
    if not os.path.isfile(path):
        return {}
    with open(path, encoding="utf-8") as fh:
        return json.load(fh).get("runs", {})
