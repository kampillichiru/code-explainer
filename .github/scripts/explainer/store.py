"""Where things are and how they are read: paths, config.json, JSON files, file fingerprints."""

import hashlib
import json
import os


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


PACKAGE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.dirname(PACKAGE)
HERE = long_path(os.path.dirname(SCRIPTS))  # the pipeline folder: config.json, steps, output


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


def read_text_file(path):
    with open(path, encoding="utf-8-sig") as fh:
        return fh.read()


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


def output_fingerprint(module, key):
    """Hashes of the files an agent writes for one work item (or for the overview). Unchanged = it wrote nothing."""
    paths = [out_dir(module, "overview.json")] if key == module + "-overview" \
        else [out_dir(module, d, key + ".json") for d in ("rules", "verify")]
    return [file_hash(p) if os.path.isfile(p) else None for p in paths]
