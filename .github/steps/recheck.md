# Step: second check of the corrections for one work item

First read `common-rules.md` in this folder and follow it.

The verify step disagreed with parts of the rules file. The resolve step then corrected those parts or added new ones. Nobody has checked the corrected text yet. You check it against the code. You did not write it, so assume it may still be wrong.

## What to do
1. Open the work item JSON file named in the chat, the file in `rules_file` and the file in `verify_file`.
2. In the verify file, find every entry that has no `recheck` field yet and that has:
   - `"resolution": "fixed"` (in `flow_verdict`, `verdicts`, `scenario_verdicts`, `requirement_verdicts` or `missed_rules`), or
   - `"verdict": "added_in_resolution"`.
3. For each one, read the code at the lines concerned, then read the rule, requirement, scenario or flow as it is in the rules file now:
   - Are the conditions, the formula, the exact values and the units the same as in the code?
   - Calculate the example again. Is the result right?
   - For a `missed_rules` entry: does the rules file now describe that behaviour correctly?
4. Add to that entry in the verify file:
   - `"recheck": "agree"` if the text now matches the code;
   - `"recheck": "disagree"` and `"recheck_reason"` with the line number if it still does not.
5. Change nothing else. Do not edit the rules file. Do not change a verdict or a resolution.
6. Run `python explain.py validate <work item id>` and fix any problem it reports in the verify file.
7. Reply with one line for each entry you checked: agree, or disagree and why.

A `disagree` is not sent back for another correction. It goes into the document as an open question, and the business expert decides.
