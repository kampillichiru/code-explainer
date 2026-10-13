# Step: resolve disagreements for one work item

First read `common-rules.md` in this folder and follow it.

The extract step wrote the rules file. The verify step disagreed with some rules, with the flow or with some scenarios, or found missed rules. You decide who is right by reading the code.

## What to do
1. Open the work item JSON file named in the chat, the file in `rules_file` and the file in `verify_file`.
2. For the `flow_verdict`, each entry in `scenario_verdicts`, `requirement_verdicts` and `verdicts` with `"verdict": "disagree"`, and each entry in `missed_rules`, that has no `resolution` yet:
   - Read the code at the lines concerned.
   - Decide, and add a `resolution` field to that entry in the verify file:
     - `"fixed"`: the reviewer was right. Correct the rules file: the rule, the requirement, the flow steps or the scenario, or add what is missing.
     - `"verifier_wrong"`: the rules file was right. Add `resolution_note` with the line that proves it.
     - `"sme_question"`: the code does not settle it. Set the rule status to `unclear` and add the question to `questions_for_sme`.
3. If you add a new rule to the rules file, link it to a box in `flow_steps` and to a requirement (a new one gets `{"requirement_id": "<new id>", "verdict": "added_in_resolution"}` in `requirement_verdicts`), and add `{"rule_id": "<new id>", "verdict": "added_in_resolution"}` to `verdicts` in the verify file.
4. If you add a new scenario, add `{"scenario_id": "<new id>", "verdict": "added_in_resolution"}` to `scenario_verdicts`. If you add a box or an arrow to `flow_steps`, some scenario must follow it.
5. Run `python explain.py validate <work item id>` and fix any problem until it passes.
6. Reply with one line per disagreement: what you decided and why.
