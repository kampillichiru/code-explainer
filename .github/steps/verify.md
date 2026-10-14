# Step: independent check of the flow, scenarios and rules for one work item

First read `common-rules.md` in this folder and follow it.

You are the second reviewer. Another reviewer wrote the rules file. Assume it may contain mistakes. Your job is to find them, not to confirm them.

## What to do
1. Open the work item JSON file named in the chat. Read every method in `methods_to_document` and work out for yourself what the code does, before you open the rules file: where it starts, every way it can end, and each decision on the way.
2. Open the file in `rules_file`. For each rule, compare it with the code at the lines in `sources`:
   - Are the conditions complete and correct (including "more than" against "more than or equal", and "and" against "or")?
   - Is the formula correct, with the right order, rounding and exact values?
   - Calculate the example again yourself from the code. Is the result right?
   - Are exceptions missing?
   - For a rule that covers a loop: is it right about what is repeated, over which records, and when it stops early?
   - For a rule that covers a fixed number: is the number, with its unit, the one in the code?
   - `values_used`: is every value listed, with the right origin and the exact fixed value, table and column?
   - `business_reason`: if `reason_basis` is `stated`, does the comment, message or business note really say it? If it is `inferred`, does the code support it? A reason that sounds likely but has no support in the code is a `disagree`.
3. Check the flow (`flow_purpose`, `starts_when`, `inputs`, `flow_steps`) against the code and give one `flow_verdict`:
   - Are the steps in the order the code runs them?
   - Does every decision have all its branches, with the right labels?
   - Is every way the code can end shown as an `end` box, including rejections and errors?
   - Does the code support `users_and_roles`, `preconditions` and `outputs`? A role or a precondition that the code does not show is a `disagree`.
4. Check each scenario and give one verdict for each:
   - Can the code really follow this path under the `when` conditions?
   - Calculate the example again from input to final result. Is the result right?
   - Is the `type` right (`main`, `alternate`, `exception`), and does `user_sees` match what the code gives back?
   - Is a real case missing, for example a combination of conditions that gives a different result? Report it under `missed_rules`.
5. Check each requirement and give one verdict for each: does the code really do what the statement says, with the same conditions, values and units? A statement that says more than the code does is a `disagree`.
   You do not check `code_runs`: a tool ran the code with those inputs, so their results are facts. Use them. A rule, a requirement or a scenario that does not agree with the result of a code run is a `disagree`.
6. Check each entry in `no_business_rule`. If the code at that line changes a business result, report it under `missed_rules`.
7. Report any business behaviour in the code that no rule describes under `missed_rules`.
8. Do not edit the rules file. Write your result to the path in `verify_file`, in the format below.
9. Run `python explain.py validate <work item id>` and fix any problem it reports in your verify file.
10. Reply with a short summary: how many rules and scenarios you agree with, and each disagreement in one line.

## Output format
```json
{
  "work_item": "AR-003",
  "flow_verdict": {"verdict": "agree"},
  "requirement_verdicts": [
    {"requirement_id": "AR-003-FR1", "verdict": "agree"}
  ],
  "scenario_verdicts": [
    {"scenario_id": "AR-003-SC1", "verdict": "agree"},
    {"scenario_id": "AR-003-SC2", "verdict": "disagree",
     "reason": "Tax is added before rounding (line 22). The example total leaves the tax out."}
  ],
  "verdicts": [
    {"rule_id": "AR-003-R1", "verdict": "agree"},
    {"rule_id": "AR-003-R2", "verdict": "disagree",
     "reason": "The code uses 'more than 5 days' (line 19). The rule says '5 days or more'."}
  ],
  "missed_rules": [
    {"description": "The total is rounded to 2 decimals, half up.",
     "file": "src/com/acme/ar/InvProc.java", "start_line": 23, "end_line": 23}
  ]
}
```

`verdict` is `agree` or `disagree`. The flow needs one verdict, and every rule, every scenario and every requirement in the rules file needs one. A `disagree` needs a `reason` with the line number.
