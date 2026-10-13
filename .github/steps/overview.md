# Step: write the overview of one module

First read `common-rules.md` in this folder and follow it.

Every flow of the module is already documented. You now write the first chapter of the document: why the module exists and what types of flow it has. You do not read Java source in this step.

## Input
The chat names three things:
- the module;
- the flows index file: one entry for each documented flow, with its id, title, summary, purpose, trigger and possible ends;
- the output file.

If the chat also names a file with notes of the business team, read it first.

## What to do
1. Read the flows index from start to end.
2. Write `module_purpose`: why this module exists and what the business uses it for. Three to five simple sentences. Build it only from the flows and from the notes of the business team. Set `purpose_basis` to `stated` if the notes of the business team say it, otherwise to `inferred`.
3. Sort the flows into types (`flow_types`). A type is a group of flows that do the same kind of business work, for example "Invoice processing", "Month end closing", "Reports". Use business names.
   - Every flow id in the index goes into exactly one type.
   - Prefer few types. A module seldom needs more than 8.
   - Flows whose index entry has `"kind": "unreached"` go into one type named "Code that nothing in this module calls".
4. For each type, write one or two sentences in `description`: what these flows do for the business and how they differ from the other types.
5. If something about the purpose of the module cannot be told from the flows, add a question to `questions_for_sme`.
6. Write the result to the output file, in the format below.
7. Run `python explain.py validate-overview <module>`. If it reports problems, fix the file and run it again until it passes.
8. Reply with two lines: the number of flow types, and the number of questions for the SME.

## Output format
```json
{
  "module": "AR",
  "module_purpose": "The module works out what a customer has to pay for an invoice. ...",
  "purpose_basis": "inferred",
  "flow_types": [
    {
      "name": "Invoice processing",
      "description": "Flows that work out the amount to collect for one invoice.",
      "flows": ["AR-001", "AR-004"]
    }
  ],
  "questions_for_sme": ["Is this module also used for credit notes?"]
}
```
