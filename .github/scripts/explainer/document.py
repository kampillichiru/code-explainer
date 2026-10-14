"""The final document: a summary page and one page for each feature. No AI is used.

Python only arranges what the agents wrote in rules/ and verify/. It writes no business text of its own.
Ids for the reader count through the whole module (FR-01, BR-01, SC-01), and every id is a link.
"""

import os
import re

from . import run_check
from .coverage import draft_banner, unread_files, unread_lines
from .markdown import cell, example_lines, flow_diagram, folded, slug
from .notes import module_domain
from .rules_check import REASON_BASIS, VALUE_SOURCES
from .state import gather, overview_state
from .store import out_dir, plain, read_json
from .verify_check import needs_recheck

UNREACHED_NOTE = "> Note: no other code in this module calls this code. Confirm if it is still used."


def settled(verdict, state):
    """Second check passed: the reviewer agreed at once, or agreed with the text after its correction."""
    if state != "DONE":
        return False
    if needs_recheck(verdict):
        return verdict.get("recheck") == "agree"
    return verdict.get("verdict") == "agree" or verdict.get("resolution") == "verifier_wrong"


def anchor(reader_id):
    return '<a id="%s"></a>' % reader_id


def main_name(module):
    return module + "-business-logic.md"


def write_lines(path, lines):
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))


# ---------------------------------------------------------------- one feature page

class FeaturePage:
    """One work item as a page of the document.

    Creating the page takes the next reader ids from 'counts' and adds this feature to them. While the
    lines are written, the page also collects what the summary needs: its open questions, the fixed
    values, and the rows of the trace table (appendix A).
    """

    def __init__(self, module, work, state, rules, verify, counts):
        self.module, self.work, self.state, self.rules = module, work, state, rules
        self.verify = verify or {}
        self.verdicts = {v.get("rule_id"): v for v in self.verify.get("verdicts", [])}
        self.sc_verdicts = {v.get("scenario_id"): v for v in self.verify.get("scenario_verdicts", [])}
        self.fr_verdicts = {v.get("requirement_id"): v for v in self.verify.get("requirement_verdicts", [])}
        self.steps = {s["id"]: s for s in rules["flow_steps"]}
        self.reqs, self.the_rules, self.scenarios = rules.get("requirements") or [], rules.get("rules", []), rules["scenarios"]

        self.fr = {q["id"]: "FR-%02d" % (counts["requirements"] + n) for n, q in enumerate(self.reqs, 1)}
        self.br = {r["id"]: "BR-%02d" % (counts["rules"] + n) for n, r in enumerate(self.the_rules, 1)}
        self.sc = {s["id"]: "SC-%02d" % (counts["scenarios"] + n) for n, s in enumerate(self.scenarios, 1)}
        counts["flows"] += 1
        counts["requirements"] += len(self.reqs)
        counts["rules"] += len(self.the_rules)
        counts["scenarios"] += len(self.scenarios)
        self.title = "2.%d %s" % (counts["flows"], rules["flow_title"])
        self.fname = "%02d-%s.md" % (counts["flows"], slug(rules["flow_title"]))

        self.runs = rules.get("code_runs") or []
        self.ran = run_check.results(out_dir(module, "exec"), work["id"])
        counts["runs"] += sum(map(self.ran_ok, self.runs))

        self.uses = {}  # scenario id -> rules on its path
        for sc in self.scenarios:
            self.uses[sc["id"]] = []
            for sid in sc["path"]:
                self.uses[sc["id"]] += [r for r in self.steps[sid].get("rules") or [] if r not in self.uses[sc["id"]]]
        self.needed_by = {r["id"]: [self.fr[q["id"]] for q in self.reqs if r["id"] in q["rules"]] for r in self.the_rules}
        self.used_in = {r["id"]: [self.sc[s["id"]] for s in self.scenarios if r["id"] in self.uses[s["id"]]]
                        for r in self.the_rules}

        self.questions = ["%s: %s" % (rules["flow_title"], q) for q in rules.get("flow_questions_for_sme") or []]
        self.fixed, self.matrix = [], []
        self.lines = self._page()

    # ---- links and marks

    def here(self, reader_id):
        """Link inside the feature page."""
        return "[%s](#%s)" % (reader_id, reader_id)

    def far(self, reader_id):
        """Link from the summary page."""
        return "[%s](features/%s#%s)" % (reader_id, self.fname, reader_id)

    def mark(self, verdict):
        return "✔" if settled(verdict, self.state) else "☐"

    def ran_ok(self, run):
        return self.ran.get(run["id"], {}).get("status") == "match"

    def unchecked(self):
        """How many parts of this feature have not passed the second check."""
        verdicts = [self.verify.get("flow_verdict") or {}] + list(self.verdicts.values()) \
            + list(self.sc_verdicts.values()) + list(self.fr_verdicts.values())
        return sum(not settled(v, self.state) for v in verdicts)

    # ---- the page

    def _page(self):
        page = self._header()
        if not self.the_rules:
            page += ["## Business behaviour", "", "None. This code changes no business result.", ""]
            page += ["- " + str(e.get("reason", "")) for e in self.rules.get("no_business_rule", [])] + [""]
        else:
            page += self._users_and_preconditions()
            page += self._requirements()
            page += self._business_rules()
            page += self._code_runs()
            page += self._flows()
            page += self._inputs_and_outputs()
        self.questions += self._still_disagreed()
        return page + ["## Open questions", ""] + (["- " + q for q in self.questions] or ["None."]) + [""]

    def _header(self):
        rules = self.rules
        page = ["# " + self.title, "", "Part of [%s - business logic](../%s). Every id on this page is a link."
                % (self.module, main_name(self.module)), ""]
        if self.state != "DONE":
            page += ["> **DRAFT - NOT READY TO USE AS REQUIREMENTS.** This feature has not passed the second "
                     "check (state: %s). It may be wrong." % self.state, ""]
        if self.work["kind"] == "unreached":
            page += [UNREACHED_NOTE, ""]
        return page + ["## Overview", "", rules["flow_summary"], "", "**Why it exists:** " + rules["flow_purpose"], "",
                       "**Starts when:** " + rules["starts_when"], ""]

    def _users_and_preconditions(self):
        rules = self.rules
        page = ["## Users and roles", "", "| Role | Allowed to |", "|---|---|"]
        page += ["| %s | %s |" % (cell(u["role"]), cell(u["allowed_to"])) for u in rules["users_and_roles"]]
        page += ["", REASON_BASIS[rules["roles_basis"]].strip(), ""] if REASON_BASIS[rules["roles_basis"]] else [""]
        return page + ["## Preconditions", ""] + ["- " + str(p) for p in rules["preconditions"]] + [""]

    def _requirements(self):
        page = ["## Functional requirements", ""]
        for q in self.reqs:
            page.append("- %s**%s:** %s (%s) Second check %s" % (
                anchor(self.fr[q["id"]]), self.fr[q["id"]], q["text"], ", ".join(self.here(self.br[r]) for r in q["rules"]),
                self.mark(self.fr_verdicts.get(q["id"], {}))))
        return page + [""]

    def _business_rules(self):
        page = ["## Business rules", ""]
        for r in self.the_rules:
            page += self._business_rule(r)
        return page

    def _business_rule(self, r):
        rid = self.br[r["id"]]
        needed_by, used_in = self.needed_by[r["id"]], self.used_in[r["id"]]
        page = ["### %s%s - %s" % (anchor(rid), rid, r["title"]), "",
                "**What it does:** " + r["what_it_does"], "", "**When it applies:**"]
        page += ["- " + c for c in r["when_it_applies"]]
        page += ["", "**How the value is calculated:** " + r["how_it_is_calculated"], "", "**Example:**"]
        page += example_lines(r["example"])
        if r.get("exceptions"):
            page += ["", "**Exceptions:**"] + ["- " + e for e in r["exceptions"]]
        executed = sum(self.ran_ok(x) for x in self.runs if x.get("rule") == r["id"])
        page += ["", "Needed by: %s. Used in: %s. Code: [appendix A](../%s#trace-%s). "
                     "Code-checked ✔ / %sSecond check %s / SME confirmed ☐%s"
                 % (", ".join(self.here(i) for i in needed_by),
                    ", ".join(self.here(i) for i in used_in) or "no scenario", main_name(self.module), rid,
                    "[Run against the code](#code-runs) ✔ (%d) / " % executed if executed else "",
                    self.mark(self.verdicts.get(r["id"], {})),
                    "  — **UNCLEAR, see open questions**" if r["status"] == "unclear" else ""), ""]
        detail = ["**Business reason:** " + r["business_reason"] + REASON_BASIS[r["reason_basis"]], "",
                  "| Value | Comes from | Exact value, column or formula |", "|---|---|---|"]
        for v in r["values_used"]:
            detail.append("| %s | %s | %s |" % (cell(v["name"]), VALUE_SOURCES[v["comes_from"]], cell(v["value"])))
            if v["comes_from"] == "fixed":
                self.fixed.append((v["name"], v["value"], self.far(rid)))
        page += folded("Business reason and the origin of each value", detail)
        self.questions += ["%s: %s" % (rid, q) for q in r.get("questions_for_sme") or []]
        self.matrix.append((rid, self.far(rid), ", ".join(self.far(i) for i in needed_by),
                            ", ".join(self.far(i) for i in used_in) or "-",
                            "; ".join("`%s` lines %s-%s" % (s["file"], s["start_line"], s["end_line"])
                                      for s in r["sources"])))
        return page

    def _code_runs(self):
        if not self.runs:
            return []
        params = {s["method"]: s["params"] for s in self.work.get("runnable_methods") or []}
        page = ['## <a id="code-runs"></a>Examples checked by running the code', "",
                "Nobody worked these results out by reading. The code itself was run with the inputs, and "
                "the result is what it returned.", "",
                "| Code that was run | Inputs | Result returned by the code | Rule | Run |", "|---|---|---|---|---|"]
        for x in self.runs:
            names = [p["name"] for p in params.get(x["method"], [])]
            got = self.ran.get(x["id"], {})
            page.append("| `%s` | %s | %s | %s | %s |" % (
                cell(x["method"]), cell("; ".join("%s = %s" % (n, "null" if a is None else a)
                                                  for n, a in zip(names, x["args"]))),
                cell("**%s**" % got["actual"] if self.ran_ok(x)
                     else "%s (not run: %s)" % (x.get("expected"), got.get("note", "no result"))),
                self.here(self.br[x["rule"]]) if x.get("rule") in self.br else "-", "✔" if self.ran_ok(x) else "☐"))
        return page + [""]

    def _scenario(self, sc):
        lines = ["When:"] + ["- " + c for c in sc["when"]]
        lines += ["", "Steps:"] + ["%d. %s" % (n, self.steps[sid]["text"]) for n, sid in enumerate(sc["path"], 1)]
        lines += ["", "Outcome: " + sc["outcome"], "", "Example:"] + example_lines(sc["example"])
        return lines + ["", "Rules used: %s. Second check %s" % (
            ", ".join(self.here(self.br[r]) for r in self.uses[sc["id"]]) or "none",
            self.mark(self.sc_verdicts.get(sc["id"], {}))), ""]

    def _flows(self):
        sc_no = self.sc
        page = ["## Main flow", ""] + flow_diagram(self.rules["flow_steps"])
        page += ["Second check of the diagram: %s" % self.mark(self.verify.get("flow_verdict") or {}), ""]
        for sc in self.scenarios:
            if sc["type"] == "main":
                page += ["%s**%s - %s**" % (anchor(sc_no[sc["id"]]), sc_no[sc["id"]], sc["title"]), ""] + self._scenario(sc)

        others = [sc for sc in self.scenarios if sc["type"] != "main"]
        page += ["## Alternate and exception flows", ""]
        if not others:
            return page + ["None.", ""]
        page += ["| Scenario | Type | When | Outcome | What the user sees | Rules |", "|---|---|---|---|---|---|"]
        page += ["| %s%s %s | %s | %s | %s | %s | %s |" % (
            anchor(sc_no[sc["id"]]), sc_no[sc["id"]], cell(sc["title"]), sc["type"].capitalize(),
            cell("; ".join(sc["when"])), cell(sc["outcome"]), cell(sc["user_sees"]),
            ", ".join(self.here(self.br[r]) for r in self.uses[sc["id"]]) or "-") for sc in others] + [""]
        for sc in others:
            page += folded("%s - steps and worked example" % sc_no[sc["id"]], self._scenario(sc))
        return page

    def _inputs_and_outputs(self):
        rules = self.rules
        page = ["## Inputs and outputs", "", "**Inputs:**"] + ["- " + str(i) for i in rules["inputs"]]
        page += ["", "**Outputs:**"] + ["- " + str(o) for o in rules["outputs"]]
        return page + ["", "**How it can end:**"] + ["- " + s["text"] for s in rules["flow_steps"] if s["kind"] == "end"] + [""]

    def _still_disagreed(self):
        """A correction that the recheck did not accept goes to the SME as an open question."""
        verify = self.verify
        still_open = [(self.rules["flow_title"], verify.get("flow_verdict") or {})]
        for key, names, entries in (("rule_id", self.br, verify.get("verdicts", [])),
                                    ("scenario_id", self.sc, verify.get("scenario_verdicts", [])),
                                    ("requirement_id", self.fr, verify.get("requirement_verdicts", []))):
            still_open += [(names.get(v.get(key), v.get(key)), v) for v in entries]
        still_open += [("A behaviour reported as missing (%s)" % m.get("description", ""), m)
                       for m in verify.get("missed_rules", [])]
        return ["%s: the two reviews still disagree after a correction. %s" % (name, v.get("recheck_reason", ""))
                for name, v in still_open if v.get("recheck") == "disagree"]

    # ---- what the summary page shows of this feature

    def link(self):
        return "[%s](features/%s)" % (self.title, self.fname)

    def numbers(self):
        return (len(self.reqs), len(self.the_rules), len(self.scenarios), len(self.questions), self.unchecked())

    def requirement_lines(self):
        return ["- **%s:** %s (%s)" % (self.far(self.fr[q["id"]]), q["text"], ", ".join(self.far(self.br[r]) for r in q["rules"]))
                for q in self.reqs]

    def entry_points(self):
        return "; ".join("`%s` (`%s` lines %s-%s)" % (e["method"], e["file"], e["start_line"], e["end_line"])
                         for e in self.work["entry_points"])


# ---------------------------------------------------------------- the summary page

def all_questions(module, pages, overview):
    """Every open question once: the module's own first, then those of each feature."""
    questions = [q for p in pages for q in p.questions]
    for q in reversed((overview or {}).get("questions_for_sme") or []):
        questions.insert(0, "%s module: %s" % (module, q))
    roles_unknown = [p.title for p in pages if p.rules["roles_basis"] == "unknown"]
    if roles_unknown:  # asked once for the module, not once in every feature
        questions.insert(0, "Users and roles: the code does not show who uses these features or what each role is "
                            "allowed to do. Please say it for: %s." % "; ".join(roles_unknown))
    seen, unique = set(), []
    for q in questions:
        key = re.sub(r"\W+", " ", q.split(":", 1)[-1]).strip().lower()
        if key not in seen:
            seen.add(key)
            unique.append(q)
    return unique


def intro_lines(module, banner):
    return ["# %s - Business logic of the current system%s" % (module, " (DRAFT)" if banner else ""), ""] + banner + [
           "Business domain: **%s**" % (module_domain(module) or "not given"), "",
           "This document describes what the current system does. It was produced from the source code.", "",
           "How to read it: this page is the summary. Chapter 2 lists each feature with its functional "
           "requirements. The title of a feature is a link to its own page, with the business rules, the flow "
           "diagram, the scenarios and the worked examples. Every id (**FR** = functional requirement, "
           "**BR** = business rule, **SC** = scenario) is a link. Appendix A links every requirement to its "
           "rule and to the lines of code.", "",
           "Status marks: **Code-checked** = passed the automatic checks. "
           "**Run against the code** = the code was run with the inputs of an example and returned the "
           "documented result (only for code that can be run on its own). "
           "**Second check** = a second, independent review agreed. "
           "**SME confirmed** = to be ticked by the business expert.", ""]


def overview_lines(overview, counts, question_count, pages):
    out = ["## 1. Module overview", ""]
    if overview:
        out += [overview["module_purpose"] + (REASON_BASIS["inferred"] if overview["purpose_basis"] == "inferred" else ""), ""]
    else:
        out += ["Not written yet. It is written when all features are documented.", ""]
    out += ["| | Number |", "|---|---|"]
    out += ["| Features | %d |" % counts["flows"],
            "| Functional requirements | %d |" % counts["requirements"],
            "| Business rules | %d |" % counts["rules"],
            "| Scenarios (ways through a feature, from start to end) | %d |" % counts["scenarios"],
            "| Examples checked by running the code | %d |" % counts["runs"],
            "| Open questions for the SME | %d |" % question_count, ""]
    by_id = {p.work["id"]: p for p in pages}
    for n, t in enumerate((overview or {}).get("flow_types", []), 1):
        out += ["**%d. %s** - %s" % (n, t["name"], t["description"]), ""]
        out += ["- " + (by_id[f].link() if f in by_id else f) for f in t["flows"]] + [""]
    return out


def feature_lines(pages, pending):
    out = ["## 2. Features", "",
           "| Feature | Requirements | Rules | Scenarios | Open questions | Not yet second-checked |", "|---|---|---|---|---|---|"]
    out += ["| %s | %d | %d | %d | %d | %d |" % ((p.link(),) + p.numbers()) for p in pages]
    out += ["| %s - not documented yet | | | | | |" % i for i in pending] + [""]
    for p in pages:
        out += ["### " + p.link(), "", p.rules["flow_summary"], ""]
        if p.work["kind"] == "unreached":
            out += [UNREACHED_NOTE, ""]
        out += p.requirement_lines() or ["No business behaviour."]
        out.append("")
    return out


def reference_lines(module, pages, questions):
    """Glossary, fixed values, open questions, files not read, and the trace from requirement to code."""
    glossary = {}
    for p in pages:
        for g in p.rules.get("glossary", []):
            glossary.setdefault(g["technical_name"], g["business_meaning"])
    fixed = [row for p in pages for row in p.fixed]
    out = []
    if glossary:
        out += ["## 3. Glossary: names in the code and their business meaning", "", "| Name in code | Business meaning |", "|---|---|"]
        out += ["| `%s` | %s |" % (k, cell(glossary[k])) for k in sorted(glossary)] + [""]
    out += ["## 4. Fixed business values", "",
            "Values that are written in the code itself. To change one of them today, the code must be changed.", ""]
    if fixed:
        out += ["| Value | Fixed at | Used in rule |", "|---|---|---|"]
        out += ["| %s | %s | %s |" % (cell(n), cell(v), rid) for n, v, rid in fixed] + [""]
    else:
        out += ["None.", ""]
    out += ["## 5. Open questions for the SME", ""] + (["- " + q for q in questions] or ["None."]) + [""]
    out += ["## 6. Files that were not read", ""] + (unread_lines(module) or ["None. Every file in the module folders was read.", ""])
    out += ["## Appendix A. From each requirement to its rule, its scenarios and the code", "",
            "| Rule | Needed by | Used in scenarios | Code lines |", "|---|---|---|---|"]
    out += ['| <a id="trace-%s"></a>%s | %s | %s | %s |' % row for p in pages for row in p.matrix]
    out += ["", "| Feature | Work item | Entry point in the code |", "|---|---|---|"]
    return out + ["| %s | %s | %s |" % (p.link(), p.work["id"], p.entry_points()) for p in pages] + [""]


# ---------------------------------------------------------------- command

def cmd_build_doc(module):
    """Writes a short summary document and one page for each feature. Every id is a link."""
    rows = gather(module)
    banner = draft_banner(rows)
    feat_dir = out_dir(module, "features")
    os.makedirs(feat_dir, exist_ok=True)
    for old in os.listdir(feat_dir):
        if old.endswith(".md"):
            os.remove(os.path.join(feat_dir, old))

    counts = {"flows": 0, "scenarios": 0, "rules": 0, "requirements": 0, "runs": 0}
    pages, pending = [], []
    for w, state, rules, verify in rows:
        if state in ("TODO", "EXTRACT_INVALID") or not rules:
            pending.append(w["id"])
            continue
        page = FeaturePage(module, w, state, rules, verify, counts)
        write_lines(os.path.join(feat_dir, page.fname), page.lines)
        pages.append(page)

    overview = read_json(out_dir(module, "overview.json")) if overview_state(module)[0] == "DONE" else None
    questions = all_questions(module, pages, overview)
    out = intro_lines(module, banner) + overview_lines(overview, counts, len(questions), pages) \
        + feature_lines(pages, pending) + reference_lines(module, pages, questions)
    path = out_dir(module, main_name(module))
    write_lines(path, out)

    print("Written: %s and %d feature pages in %s" % (plain(path), len(pages), plain(feat_dir)))
    if banner:
        print("DRAFT: %d of %d work items are not DONE. The document is marked as a draft."
              % (sum(r[1] != "DONE" for r in rows), len(rows)))
    unread = unread_files(module)
    if unread:
        print("NOT READ: %d file(s) in the module folders were not read. See chapter 6 of the document."
              % sum(map(len, unread.values())))
