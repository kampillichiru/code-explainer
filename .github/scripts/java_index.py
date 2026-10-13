"""Reads Java source files and lists methods, calls and the items that must be explained.

No AI is used here. The output is the checklist that the AI stages must cover.
"""
import bisect
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "vendor"))
import javalang  # noqa: E402
from javalang import tree as T  # noqa: E402

SQL_RE = re.compile(r"\b(SELECT|INSERT\s+INTO|UPDATE|DELETE\s+FROM|MERGE\s+INTO|CALL)\b", re.I)
FALLBACK_RE = {
    "if": re.compile(r"\bif\s*\("),
    "case": re.compile(r"\bcase\b"),
    "catch": re.compile(r"\bcatch\s*\("),
    "loop": re.compile(r"\b(while|for)\s*\("),
}
JDK_TYPES = set(
    "String StringBuilder StringBuffer Object Integer Long Double Float Short Byte Boolean Character "
    "BigDecimal BigInteger Math List ArrayList LinkedList Map HashMap TreeMap LinkedHashMap Hashtable "
    "Set HashSet TreeSet Vector Iterator Collection Collections Arrays Date Calendar GregorianCalendar "
    "SimpleDateFormat DecimalFormat NumberFormat System Logger Log Exception Throwable Thread "
    "Connection Statement PreparedStatement CallableStatement ResultSet Enumeration Properties "
    "Optional Stream Objects Locale".split()
)


def read_text(path):
    data = open(path, "rb").read()
    for enc in ("utf-8", "cp1252"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            pass
    return data.decode("latin-1")


def _tname(t):
    if t is None:
        return None
    name = t.name
    sub = getattr(t, "sub_type", None)
    while sub is not None:
        name = sub.name
        sub = getattr(sub, "sub_type", None)
    return name


def _line(node):
    pos = getattr(node, "position", None)
    return pos[0] if pos else None


def _method_end(tokens, tok_lines, start_line):
    """Line of the closing brace of the method that starts at start_line."""
    i = bisect.bisect_left(tok_lines, start_line)
    paren = 0
    while i < len(tokens):
        v = tokens[i].value
        if v == "(":
            paren += 1
        elif v == ")":
            paren -= 1
        elif paren == 0 and v == ";":
            return tok_lines[i], False
        elif paren == 0 and v == "{":
            depth = 0
            while i < len(tokens):
                v = tokens[i].value
                if v == "{":
                    depth += 1
                elif v == "}":
                    depth -= 1
                    if depth == 0:
                        return tok_lines[i], True
                i += 1
            break
        i += 1
    return tok_lines[-1], True


def _plain_body(tokens, tok_lines, start, end):
    """True when the body only reads or stores a value: no calculation, no comparison, no call."""
    i = bisect.bisect_left(tok_lines, start)
    while i < len(tokens) and tok_lines[i] <= end and tokens[i].value != "{":
        i += 1
    for tok in tokens[i:]:
        if tok.position[0] > end:
            break
        if tok.value in ("(", "new") or (isinstance(tok, javalang.tokenizer.Operator) and tok.value != "="):
            return False
    return True


def _token_items(tokens, kinds):
    """Decision points and SQL statements found in the token list: (line, kind)."""
    out = []
    for i, tok in enumerate(tokens):
        v = tok.value
        line = tok.position[0]
        kind = None
        if isinstance(tok, javalang.tokenizer.Keyword):
            if v == "if":
                kind = "if"
            elif v == "case":
                kind = "case"
            elif v == "catch":
                kind = "catch"
            elif v in ("while", "for"):
                kind = "loop"
            elif v == "default" and i + 1 < len(tokens) and tokens[i + 1].value == ":":
                kind = "case"
        elif v == "?":
            prev = tokens[i - 1].value if i else ""
            nxt = tokens[i + 1].value if i + 1 < len(tokens) else ""
            wildcard = prev in ("<", ",") and nxt in (">", ",", "extends", "super", ">>", ">>>")
            if not wildcard:
                kind = "ternary"
        elif isinstance(tok, javalang.tokenizer.String) and SQL_RE.search(v):
            kind = "sql"
        if kind and kind in kinds:
            out.append((line, kind))
    return out


FILE_TYPES = {
    "java": [".java"],
    "sql": [".sql", ".ddl", ".pks", ".pkb", ".prc", ".fnc", ".trg"],
    "config": [".properties", ".xml", ".yml", ".yaml", ".ini", ".conf", ".cfg"],
}


def file_type(name, file_types=None):
    ext = os.path.splitext(name)[1].lower()
    for kind, exts in (file_types or FILE_TYPES).items():
        if ext in exts:
            return kind
    return None


def index_module(source_root, module_dirs, kinds, file_types=None):
    """Returns {files, classes, methods}. Paths are relative to source_root with '/'."""
    files, classes, methods = {}, {}, {}
    for module_dir in module_dirs:
        for dirpath, _dirs, names in os.walk(module_dir):
            for name in sorted(names):
                kind = file_type(name, file_types)
                path = os.path.join(dirpath, name)
                rel = os.path.relpath(path, source_root).replace("\\", "/")
                if kind == "java":
                    _index_file(path, rel, kinds, files, classes, methods)
                elif kind == "sql":
                    _index_sql(path, rel, kinds, files, methods)
                elif kind == "config":
                    _index_config(path, rel, kinds, files, methods)
    return {"files": files, "classes": classes, "methods": methods}


# ---------------------------------------------------------------- SQL scripts and configuration files
# These have no parser. They are cut into units by pattern, and each unit takes the place of a method.

CREATE_RE = re.compile(
    r"^\s*CREATE\s+(?:OR\s+REPLACE\s+)?(?:(?:EDITIONABLE|NONEDITIONABLE|UNIQUE|GLOBAL|TEMPORARY|TEMP|MATERIALIZED|FORCE)\s+)*"
    r"(PROCEDURE|PROC|FUNCTION|TRIGGER|VIEW|PACKAGE\s+BODY|PACKAGE|TABLE|INDEX|SEQUENCE|TYPE|SYNONYM)\s+"
    r"(?:IF\s+NOT\s+EXISTS\s+)?([\w.$#\"\[\]`]+)", re.I)
SQL_LINE_RE = [  # first match wins
    ("catch", re.compile(r"^\s*(EXCEPTION\b|WHEN\s+OTHERS\b|BEGIN\s+CATCH\b|DECLARE\s+.*\bHANDLER\b)", re.I)),
    ("if", re.compile(r"^\s*(IF|ELSIF|ELSEIF|ELSE\s+IF)\b", re.I)),
    ("case", re.compile(r"\bWHEN\b.*\bTHEN\b", re.I)),
    ("sql", re.compile(r"^\s*(SELECT|INSERT|UPDATE|DELETE|MERGE|CREATE|ALTER|DROP|TRUNCATE|CALL|EXEC|EXECUTE)\b", re.I)),
]
CALLABLE_SQL = ("PROCEDURE", "PROC", "FUNCTION", "PACKAGE", "PACKAGE BODY")
KEY_RE = re.compile(r"^\s*([\w.\-]+)\s*[=:]")
CONFIG_COMMENT_RE = re.compile(r"^\s*(#|;|!|//|<!--|<\?xml)")
SECRET_RES = [
    (re.compile(r"(?i)((?:\w*pass\w*|pwd|\w*secret\w*|\w*token\w*|\w*key|credential\w*)\s*[=:]\s*).+"), r"\1***"),
    (re.compile(r"(?i)(<[^>]*(?:pass|pwd|secret|token|key)[^>]*>)[^<]+"), r"\1***"),
]


def _unit(rel, name, start, end, items):
    return {
        "id": "%s#%s:%d" % (rel, name, start), "cls": None, "name": name, "file": rel,
        "start": start, "end": end, "nparams": 0, "private": False, "has_body": True,
        "calls": [], "vars": {}, "items": items, "trivial": False,
    }


def _cut(src_lines, start, end, size):
    """Splits lines start..end into ranges of at most 'size' lines, cutting after a blank line or a ';'."""
    a = start
    while a <= end:
        b = min(a + size - 1, end)
        if b < end:
            for c in range(b, a + size // 2, -1):
                text = src_lines[c - 1].strip()
                if not text or text.endswith(";"):
                    b = c
                    break
        yield a, b
        a = b + 1


def _index_sql(path, rel, kinds, files, methods):
    src_lines = read_text(path).splitlines()
    files[rel] = {"lines": len(src_lines), "parsed": True}
    starts = [(n, CREATE_RE.match(line)) for n, line in enumerate(src_lines, 1)]
    starts = [(n, m) for n, m in starts if m]
    ranges = []  # (start, end, name, sql object name or None)
    first = starts[0][0] if starts else len(src_lines) + 1
    for a, b in _cut(src_lines, 1, first - 1, 200):
        ranges.append((a, b, "(script)", None))
    for i, (n, m) in enumerate(starts):
        last = starts[i + 1][0] - 1 if i + 1 < len(starts) else len(src_lines)
        end = next((k for k in range(n, last + 1) if src_lines[k - 1].strip().upper() in ("/", "GO")), last)
        kind = " ".join(m.group(1).upper().split())
        name = m.group(2).strip('"[]`')
        ranges.append((n, end, "%s %s" % (kind, name), name.split(".")[-1].lower() if kind in CALLABLE_SQL else None))
        for a, b in _cut(src_lines, end + 1, last, 200):
            ranges.append((a, b, "(script)", None))
    for a, b, name, obj in ranges:
        pairs = []
        for n in range(a, b + 1):
            code = src_lines[n - 1].split("--", 1)[0]
            for kind, rx in SQL_LINE_RE:
                if rx.search(code):
                    if kind in kinds:
                        pairs.append((n, kind))
                    break
        if not pairs:
            if not any(src_lines[n - 1].split("--", 1)[0].strip() for n in range(a, b + 1)):
                continue  # only blank lines and comments
            pairs = [(a, "method")]
        u = _unit(rel, name, a, b, _make_items(rel, src_lines, pairs))
        if obj and len(obj) >= 4:
            u["sql_object"] = obj
        methods[u["id"]] = u


def _index_config(path, rel, kinds, files, methods):
    """One item per block of settings. The whole block must be explained or marked as technical."""
    src_lines = read_text(path).splitlines()
    files[rel] = {"lines": len(src_lines), "parsed": True}
    if "config" not in kinds:
        return
    for a, b in _cut(src_lines, 1, len(src_lines), 40):
        first = next((n for n in range(a, b + 1)
                      if src_lines[n - 1].strip() and not CONFIG_COMMENT_RE.match(src_lines[n - 1])), None)
        if first is None:
            continue
        u = _unit(rel, "(settings)", a, b, _make_items(rel, src_lines, [(first, "config")]))
        keys = [KEY_RE.match(src_lines[n - 1]) for n in range(a, b + 1)]
        u["config_keys"] = {k.group(1) for k in keys if k and len(k.group(1)) >= 4}
        methods[u["id"]] = u


def _whole_file_method(rel, src_lines, items):
    return {
        "id": "%s#(whole file):1" % rel, "cls": None, "name": "(whole file)", "file": rel,
        "start": 1, "end": len(src_lines), "nparams": 0, "private": False, "has_body": True,
        "calls": [], "vars": {}, "items": items, "trivial": False,
    }


def _make_items(rel, src_lines, pairs):
    seen, items = {}, []
    for line, kind in pairs:
        key = "%s:%d:%s" % (rel, line, kind)
        seen[key] = seen.get(key, 0) + 1
        if seen[key] > 1:
            key = "%s:%d" % (key, seen[key])
        text = src_lines[line - 1].strip()[:200] if line <= len(src_lines) else ""
        if kind == "config":  # never copy a password or key into a work item
            for rx, masked in SECRET_RES:
                text = rx.sub(masked, text)
        items.append({"id": key, "kind": kind, "file": rel, "line": line, "text": text})
    return items


def _index_file(path, rel, kinds, files, classes, methods):
    text = read_text(path)
    src_lines = text.splitlines()
    files[rel] = {"lines": len(src_lines), "parsed": True}
    try:
        tokens = list(javalang.tokenizer.tokenize(text))
        unit = javalang.parser.Parser(tokens).parse()
    except Exception as exc:  # code the parser cannot read: document the whole file as one unit
        files[rel]["parsed"] = False
        files[rel]["error"] = "%s: %s" % (type(exc).__name__, str(exc)[:120])
        pairs = []
        for n, line in enumerate(src_lines, 1):
            for kind, rx in FALLBACK_RE.items():
                if kind in kinds and rx.search(line):
                    pairs.append((n, kind))
            if "sql" in kinds and SQL_RE.search(line) and '"' in line:
                pairs.append((n, "sql"))
        m = _whole_file_method(rel, src_lines, _make_items(rel, src_lines, pairs))
        methods[m["id"]] = m
        return

    tok_lines = [t.position[0] for t in tokens]
    package = unit.package.name if unit.package else ""
    imports = [i.path for i in unit.imports]
    selector_calls = set()
    for _p, node in unit:
        for sel in getattr(node, "selectors", None) or []:
            if isinstance(sel, T.MethodInvocation):
                selector_calls.add(id(sel))

    file_methods = []
    for _p, node in unit.filter(T.TypeDeclaration):
        simple = node.name
        fqn = (package + "." if package else "") + simple
        members = node.body.declarations if isinstance(node, T.EnumDeclaration) else node.body
        fields = {}
        for mem in members or []:
            if isinstance(mem, T.FieldDeclaration):
                for d in mem.declarators:
                    fields[d.name] = _tname(mem.type)
        ext = getattr(node, "extends", None)
        if isinstance(ext, list):
            parents = [_tname(e) for e in ext]
        else:
            parents = [_tname(ext)] if ext else []
        parents += [_tname(i) for i in (getattr(node, "implements", None) or [])]
        classes[fqn] = {
            "simple": simple, "package": package, "file": rel, "parents": parents,
            "fields": fields, "imports": imports,
            "interface": isinstance(node, T.InterfaceDeclaration),
        }
        for mem in members or []:
            if not isinstance(mem, (T.MethodDeclaration, T.ConstructorDeclaration)):
                continue
            start = _line(mem)
            if start is None:
                continue
            end, has_body = _method_end(tokens, tok_lines, start)
            variables = {}
            for p in mem.parameters:
                variables[p.name] = _tname(p.type)
            for _q, v in mem.filter(T.VariableDeclaration):
                for d in v.declarators:
                    variables[d.name] = _tname(v.type)
            calls = []
            for _q, c in mem.filter(T.MethodInvocation):
                qual = "<chained>" if id(c) in selector_calls else (c.qualifier or "")
                calls.append([qual, c.member, len(c.arguments or [])])
            name = mem.name if isinstance(mem, T.MethodDeclaration) else "<init>"
            m = {
                "id": "%s#%s.%s:%d" % (rel, simple, name, start), "cls": fqn, "name": name,
                "file": rel, "start": start, "end": end, "nparams": len(mem.parameters),
                "private": "private" in (mem.modifiers or ()), "has_body": has_body,
                "calls": calls, "vars": variables, "items": [], "trivial": False,
            }
            methods[m["id"]] = m
            file_methods.append(m)

    # give every decision point to the smallest method that contains its line
    leftovers = []
    per_method = {}
    for line, kind in _token_items(tokens, kinds):
        best = None
        for m in file_methods:
            if m["start"] <= line <= m["end"]:
                if best is None or (m["end"] - m["start"]) < (best["end"] - best["start"]):
                    best = m
        if best is None:
            leftovers.append((line, kind))
        else:
            per_method.setdefault(best["id"], []).append((line, kind))
    for tok in tokens:
        if isinstance(tok, javalang.tokenizer.String):
            inside = [m for m in file_methods if m["start"] <= tok.position[0] <= m["end"]]
            if inside:
                min(inside, key=lambda m: m["end"] - m["start"]).setdefault("strings", set()).add(tok.value[1:-1])
    for m in file_methods:
        m["items"] = _make_items(rel, src_lines, per_method.get(m["id"], []))
        length = m["end"] - m["start"] + 1
        accessor = re.match(r"(get|set|is)[A-Z_]", m["name"]) and length <= 4
        if not m["items"]:
            # a short method is left out only when it just reads or stores a value
            if not m["has_body"] or ((accessor or length <= 2) and _plain_body(tokens, tok_lines, m["start"], m["end"])):
                m["trivial"] = True
            else:  # no branch, but it may hold a formula: the method itself must be explained
                m["items"] = _make_items(rel, src_lines, [(m["start"], "method")])
    if leftovers:
        m = _whole_file_method(rel, src_lines, _make_items(rel, src_lines, leftovers))
        m["id"] = "%s#(code outside methods):1" % rel
        m["name"] = "(code outside methods)"
        methods[m["id"]] = m


def resolve_calls(index):
    """Adds 'callees' (method ids inside the module) and 'external' (calls that leave it)."""
    classes, methods = index["classes"], index["methods"]
    by_simple, by_class, by_name = {}, {}, {}
    for fqn, c in classes.items():
        by_simple.setdefault(c["simple"], []).append(fqn)
    for mid, m in methods.items():
        if m["cls"]:
            by_class.setdefault(m["cls"], {}).setdefault(m["name"], []).append(mid)
            by_name.setdefault(m["name"], set()).add(m["cls"])
    children = {}
    for fqn, c in classes.items():
        for p in c["parents"]:
            for pf in by_simple.get(p, []):
                children.setdefault(pf, set()).add(fqn)

    def pick(simple, ctx):
        cands = by_simple.get(simple, [])
        if len(cands) > 1:
            c = classes[ctx]
            near = [f for f in cands if f in c["imports"] or classes[f]["package"] == c["package"]]
            cands = near or cands
        return cands

    def family(fqn):
        """The class, the classes it extends, and every subclass or implementation."""
        seen, todo = set(), [fqn]
        while todo:
            f = todo.pop()
            if f in seen:
                continue
            seen.add(f)
            todo.extend(children.get(f, ()))
        todo = [fqn]
        while todo:
            f = todo.pop()
            for p in classes[f]["parents"]:
                for pf in pick(p, f):
                    if pf not in seen:
                        seen.add(pf)
                        todo.append(pf)
        return seen

    def field_type(fqn, name):
        for f in family(fqn):
            if name in classes[f]["fields"]:
                return classes[f]["fields"][name]
        return None

    sql_objects = {m["sql_object"]: mid for mid, m in methods.items() if m.get("sql_object")}
    setting_blocks = {k: mid for mid, m in methods.items() for k in m.get("config_keys", ())}
    for m in methods.values():
        callees, external = set(), set()
        cls = m["cls"]
        for qual, name, nargs in m["calls"] if cls else []:
            targets, type_name = set(), None
            if qual == "<chained>":
                owners = by_name.get(name, ())
                if 0 < len(owners) <= 3:
                    targets = set(owners)
            elif qual in ("", "this", "super"):
                targets = family(cls)
            else:
                q = qual[5:] if qual.startswith("this.") else qual
                first = q.split(".")[0]
                type_name = m["vars"].get(first) or field_type(cls, first)
                if type_name is None and q.split(".")[-1] in by_simple:
                    type_name = q.split(".")[-1]
                for f in pick(type_name, cls) if type_name else []:
                    targets |= family(f)
            found = []
            for f in targets:
                found += by_class.get(f, {}).get(name, [])
            exact = [x for x in found if methods[x]["nparams"] == nargs]
            for x in exact or found:
                if x != m["id"]:
                    callees.add(x)
            if not found and type_name and type_name not in JDK_TYPES and type_name[:1].isupper():
                external.add("%s.%s" % (type_name, name))
        # an SQL statement that names a stored procedure or function of this module calls it
        for item in m["items"]:
            if item["kind"] == "sql":
                for word in set(re.findall(r"[\w$#]+", item["text"].lower())):
                    if word in sql_objects and sql_objects[word] != m["id"]:
                        callees.add(sql_objects[word])
        m["callees"] = sorted(callees)
        # settings this code reads by name: shown to the reader as context, documented with their own file
        m["reads"] = sorted({setting_blocks[t] for t in m.get("strings", ()) if t in setting_blocks})
        m["external"] = sorted(external)
    return index
