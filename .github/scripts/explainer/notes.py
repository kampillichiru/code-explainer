"""The module notes (module-info.md): the business domain, what the business team says, its terms.

These come from people, never from the code. Every agent reads them first."""

import os
import re

from .store import out_dir, read_text_file


NOTES_DOMAIN, NOTES_ABOUT, NOTES_TERMS = "Business domain", "What the business team says", "Business terms and roles"


def notes_section(text, heading):
    found = re.search(r"^## %s[ \t]*\n(.*?)(?=^## |\Z)" % re.escape(heading), text, re.M | re.S)
    return found.group(1).strip() if found else ""


def module_notes(module):
    path = out_dir(module, "module-info.md")
    return read_text_file(path) if os.path.isfile(path) else ""


def module_domain(module):
    """The business domain given for this module, for example 'Order management'. Empty if none was given."""
    return " ".join(notes_section(module_notes(module), NOTES_DOMAIN).split())


def write_module_notes(module, domain, about, terms):
    lines = ["# Module notes - %s" % module, "",
             "Given by the business team, not taken from the code. Every agent reads this before it reads the code.", "",
             "## " + NOTES_DOMAIN, "", domain, ""]
    for heading, text in ((NOTES_ABOUT, about), (NOTES_TERMS, terms)):
        if text:
            lines += ["## " + heading, "", text.strip(), ""]
    path = out_dir(module, "module-info.md")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))
    return "\n".join(lines)
