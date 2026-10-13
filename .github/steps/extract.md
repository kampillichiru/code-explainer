# Step: extract the flow, scenarios and business rules for one work item

First read `common-rules.md` in this folder and follow it.

## Input
The work item JSON file named in the chat. It contains:
- `entry_points`: where this flow starts in the code.
- `methods_to_document`: the code you must explain (file, start line, end line).
- `context_methods`: code that is called from there. Read it when you need it to understand a value. It is documented in another work item, so do not write rules for it.
- `items_to_cover`: every condition, SQL statement and calculation in the code you must explain. Each one has an `id`.
- `calls_to_other_modules`: calls that leave this module. Mention them by name; do not guess what they do.
- Some entries are not Java. `PROCEDURE ...`, `FUNCTION ...`, `TRIGGER ...`, `VIEW ...` or `(script)` is a part of an SQL file. `(settings)` is a block of a configuration file: its one item stands for every setting in those lines, so read them all, write a rule for each setting that changes a business result, and cover the item with those rules. Mark the item `no_business_rule` only if every setting in the block is technical.
- `kind`: if it is `unreached`, no other code in this module calls this code. Document it anyway.

## What to do
1. Read every method in `methods_to_document`, from start line to end line.
2. Work out the business rules. One rule is one business decision or one calculation. Several items often belong to one rule, for example a check and the calculation that depends on it.
3. For every rule, write:
   - the business reason (`business_reason` and `reason_basis`, see rule 12 of the common rules);
   - every value it uses or produces and where each one comes from (`values_used`, see rule 11);
   - a worked example with real numbers. Calculate the result step by step from the code, and check your arithmetic.
4. Describe the flow from the entry point to every possible end (`flow_steps`). This becomes the diagram, so keep it simple:
   - One box is one business step, not one line of code. Aim for 12 boxes or fewer for each entry point. The detail belongs in the rules, not in the boxes.
   - Box text is short, in business words: "Count the days late", "Is the customer active?".
   - A repeated part is one box ("For each invoice line: add the line amount"). Do not draw the loop.
   - Every way the code can finish is its own `end` box, including rejections and errors.
   - Link each box to the rules that describe it. Every rule must be linked to at least one box.
5. List the scenarios (`scenarios`). A scenario is one complete way through the flow, from the start box to one end box. Write enough scenarios so that every arrow of the diagram is followed by at least one of them. For each scenario give the conditions, the outcome, and one worked example with real numbers from input to final result.
6. Give each scenario a `type`: `main` for the normal case (the flow does what it exists to do), `alternate` for another valid way through, `exception` when something is missing, invalid or fails. At least one scenario is `main`. For every `alternate` and `exception` scenario, write `user_sees`: what the user or the calling system gets back (the message text, the status, the error). If the code does not show it, write "Not known from the code".
7. Write the functional requirements (`requirements`). One statement for one behaviour, in the form "The system shall ...". Use business words, with the exact values and their units. No code names in the text. Link each requirement to the rules that describe it. Every rule belongs to at least one requirement.

   | In the code | Write |
   |---|---|
   | `if (d > grace)`, then interest is added | The system shall add late payment interest when a payment is more than 5 days late. |
   | `retryCount = 3` in a configuration file | The system shall retry a failed connection up to 3 times before it reports an error. |
   | `status = "PENDING_APPROVAL"` | An order above the approval limit shall stay pending until a manager approves it. |

8. Describe who uses the flow and what surrounds it:
   - `users_and_roles`: who uses this flow and what each role is allowed to do. Take it only from what the code shows (a permission check, a role name, a user type) or from the notes of the business team. Set `roles_basis` to `stated`, `inferred` or `unknown`. If the code shows nothing, write one entry with the role "Not known from the code" and set `roles_basis` to `unknown`. Do not add a question for it: the document asks the SME once for the whole module.
   - `preconditions`: what must be true before the flow can run, for example "The customer exists and is active". Write "None found in the code" if there is none.
   - `outputs`: what comes out, in business names, for example "Total amount to collect, rounded to 2 decimals".
9. Go through `items_to_cover` one by one. Each `id` must appear either in the `covers` list of one rule, or in `no_business_rule` with a reason (for example: technical check, logging, closing a database connection).
10. Write the result to the path in `rules_file`, in the format below.
11. Run `python explain.py validate <work item id>`. If it reports problems, fix the rules file and run it again until it passes.
12. Reply with a short summary: number of requirements, number of scenarios, number of rules, number of unclear rules, and the questions for the SME.

## Keep it short

A long document is not read. The validator rejects a file that goes over these limits.

| What | Limit |
|---|---|
| `flow_summary` | 60 words |
| `flow_purpose`, `starts_when` | 40 words each |
| Text of one flow box | 12 words |
| One requirement | 45 words, and the word "shall" once only. If it says two things, write two requirements. |
| Rule `title` | 10 words |
| `what_it_does` | 40 words |
| `business_reason` | 35 words |
| `how_it_is_calculated` | 45 words |
| `when_it_applies` | 6 conditions, 25 words each |
| Steps of one example | 6 |
| Scenarios in one file | 10 |
| Scenario `title` | 10 words; `outcome` and `user_sees` 30 words each |
| Questions for the SME | 3 for each rule and 3 for the flow, 35 words each. Ask only what the SME must decide. |

Two more rules:
- Every `decision` box names the rule that describes it in `rules`.
- Code with no business behaviour (every item goes to `no_business_rule`, so there are no rules and no requirements) gets the short form: three boxes (start, one step, end), one `main` scenario, and no more than one question.

## Output format
```json
{
  "work_item": "AR-003",
  "flow_title": "Short business name of this flow",
  "flow_summary": "Two or three simple sentences: what this part of the system does.",
  "flow_purpose": "Why this flow exists: the business need it serves. If the code does not show it, say 'Not known from the code' and ask the SME in a rule.",
  "starts_when": "What triggers it, for example: each time an invoice is processed.",
  "inputs": ["Customer id", "Invoice amount", "Due date", "Processing date"],
  "outputs": ["Total amount to collect, rounded to 2 decimals"],
  "users_and_roles": [{"role": "Not known from the code", "allowed_to": "Not known from the code"}],
  "roles_basis": "unknown",
  "preconditions": ["The customer exists and is active."],
  "flow_questions_for_sme": ["Who starts invoice processing: a user or a nightly job?"],
  "flow_steps": [
    {"id": "S1", "kind": "start", "text": "Invoice is received", "next": "S2"},
    {"id": "S2", "kind": "decision", "text": "Is the customer active?", "rules": ["AR-003-R1"],
     "branches": [{"label": "Yes", "to": "S3"}, {"label": "No", "to": "E1"}]},
    {"id": "S3", "kind": "decision", "text": "More than 5 days late?", "rules": ["AR-003-R2"],
     "branches": [{"label": "Yes", "to": "S4"}, {"label": "No", "to": "E2"}]},
    {"id": "S4", "kind": "step", "text": "Add late payment interest", "rules": ["AR-003-R2"], "next": "E2"},
    {"id": "E1", "kind": "end", "text": "Rejected: no customer"},
    {"id": "E2", "kind": "end", "text": "Total to collect is returned"}
  ],
  "scenarios": [
    {
      "id": "AR-003-SC1",
      "title": "Invoice paid late",
      "type": "main",
      "when": ["The customer is active.", "The invoice is more than 5 days late."],
      "path": ["S1", "S2", "S3", "S4", "E2"],
      "outcome": "The total is the invoice amount plus interest.",
      "example": {
        "inputs": {"Invoice amount": "10,000.00", "Yearly rate": "12%", "Days late": "30"},
        "steps": ["Customer is active", "30 is more than 5, so interest is due", "Interest = 98.63"],
        "result": "Total = 10,098.63"
      }
    }
  ],
  "requirements": [
    {"id": "AR-003-FR1",
     "text": "The system shall add late payment interest when a payment is more than 5 days late and the customer is not exempt.",
     "rules": ["AR-003-R2"]}
  ],
  "rules": [
    {
      "id": "AR-003-R2",
      "title": "Late payment interest",
      "what_it_does": "Adds interest when a customer pays after the due date.",
      "business_reason": "Customers who pay late are charged for the delay.",
      "reason_basis": "inferred",
      "when_it_applies": ["The payment is more than 5 days late.", "The customer is not marked as exempt."],
      "how_it_is_calculated": "Invoice amount x yearly rate / 365 x days late.",
      "values_used": [
        {"name": "Invoice amount", "value": "Amount of the invoice being processed", "comes_from": "input"},
        {"name": "Yearly rate", "value": "CUST_MASTER.RT", "comes_from": "database"},
        {"name": "Days in a year", "value": "365", "comes_from": "fixed"},
        {"name": "Free days before interest", "value": "5", "comes_from": "fixed"},
        {"name": "Interest", "value": "Invoice amount x yearly rate / 365 x days late", "comes_from": "calculated"}
      ],
      "example": {
        "inputs": {"Invoice amount": "10,000.00", "Yearly rate": "12%", "Days late": "30"},
        "steps": ["12% / 365 = 0.0003287671 per day", "10,000.00 x 0.0003287671 x 30 = 98.63"],
        "result": "Interest = 98.63"
      },
      "exceptions": ["Government customers: 15 days, not 5."],
      "sources": [{"file": "src/com/acme/ar/InvProc.java", "start_line": 17, "end_line": 21}],
      "covers": ["src/com/acme/ar/InvProc.java:19:if"],
      "status": "clear",
      "questions_for_sme": []
    }
  ],
  "no_business_rule": [
    {"item": "src/com/acme/ar/CustDao.java:9:method", "reason": "Technical: opens the database connection."}
  ],
  "glossary": [
    {"technical_name": "exFlg", "business_meaning": "Customer is exempt from late payment interest"}
  ]
}
```
(The example is shortened: it shows one scenario and one rule. A real file has a rule for every id used in `flow_steps`, and scenarios for every arrow.)

Rules for the format:
- Rule `id` is the work item id plus `-R1`, `-R2`, and so on. Scenario `id` is the work item id plus `-SC1`, `-SC2`, and so on.
- `flow_steps`: `id` is one capital letter and a number (`S1`, `E1`). `kind` is `start`, `step`, `decision` or `end`. A `start` and a `step` have `next`. A `decision` has two or more `branches`, each with a `label` and a `to`. An `end` has neither. One `start` for each entry point. At most 25 boxes.
- `scenarios`: `path` lists the box ids in order. It begins at a `start` box, follows the arrows, and stops at an `end` box. `type` is `main`, `alternate` or `exception`. An `alternate` or `exception` scenario also has `user_sees`.
- `requirements`: `id` is the work item id plus `-FR1`, `-FR2`, and so on. `text` is one "shall" statement. `rules` lists the rule ids it rests on. A file with no rules has no requirements.
- `users_and_roles`: each entry has `role` and `allowed_to`. `roles_basis` is `stated`, `inferred` or `unknown`. - `flow_questions_for_sme`: questions about the flow as a whole. Questions about one rule go into that rule.
- `how_it_is_calculated`: write "No calculation" if the rule only decides something.
- `values_used`: `comes_from` is one of `input`, `database`, `fixed`, `calculated`, `config`, `other_module`, `system`. For `config` give the setting name and its value, not the file name (the file goes into `sources`). For `database` give table and column. For `fixed` give the exact value from the code. For `calculated` give the formula.
- `reason_basis` is `stated`, `inferred` or `unknown`. With `unknown`, add a question to `questions_for_sme`.
- `sources` use the same file paths as the work item. A source range must contain the line of every item the rule covers.
- `status` is `clear` or `unclear`. An unclear rule needs at least one entry in `questions_for_sme`.
- An error handler that changes a business result (for example "if the database fails, treat the customer as not found") is a business rule, not a technical item.
