"""Small helpers that write Markdown: table cells, the flow diagram, folded detail."""

import re


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


def slug(text):
    return re.sub(r"[^a-z0-9]+", "-", str(text).lower()).strip("-")[:50] or "feature"


def folded(summary, lines):
    """Detail the reader opens when needed. It keeps the page short."""
    return ["<details><summary>%s</summary>" % summary, ""] + lines + ["", "</details>", ""]
