# Step: compare the document with the rules the business expert listed

First read `common-rules.md` in this folder and follow it.

A business expert (SME) wrote down the rules of this module from memory, without looking at the document. You compare that list with the document, one SME rule at a time. The result is used to measure how much the tool misses and gets wrong, so do not be kind to the document and do not be kind to the SME: say what is the case.

## Input
The chat names:
- the module and its folders (the source code);
- the SME rules file: a list of `{"id": "SME-01", "text": "..."}`;
- the document rules file: every rule of the document, with its id, feature, title, what it does, when it applies, how it is calculated, its fixed values, its requirements and the code lines it comes from;
- the output file.

## What to do
For each SME rule, in order:

1. Look for the rules of the document that describe the same behaviour. The words will differ: the SME writes "we charge interest after a week", the document writes "late payment interest when more than 5 days late". Compare the meaning: the same condition, the same values with the same units, the same result. One SME rule can match several document rules, and one document rule can match several SME rules.
2. Give one verdict:
   - `same`: the document says the same thing. A value the SME left out is not a difference. A value that is different is.
   - `differs`: the document describes this behaviour, but a condition, a value, a unit or a result is not the same (5 days against 7 days, "more than" against "at least", 18% against 20%).
   - `missing`: no rule of the document describes this behaviour.
3. For `differs`: read the code at the lines the document rule comes from, and say whom the code agrees with in `code_supports`: `document`, `sme` or `neither`. Give the file and the lines you read, and say the difference in one sentence in `difference`, with both values.
4. For `missing`: search the code of the module folders for it. Search for the values (a rate, a number of days, a status code), for table and column names, and for words of the rule in names, comments and messages.
   - If the code does it: `"found_in_code": true`, with the file and the lines, and a `note` saying what the code does there.
   - If you do not find it: `"found_in_code": false`, with the words and values you searched for in `searched_for`, and a `note`. Do not guess where else it might be.
5. Write the result to the output file, in the format below. Do not change any other file.
6. Run `python explain.py calibrate <module>`. If it lists problems, fix them in your file and run it again. When it writes the report, you are done.
7. Reply with one line: how many are the same, how many differ, how many are missing.

Do not judge whether the SME is right about the business. Only say what the document says and what the code does.

## Output format
```json
{
  "module": "AR",
  "comparisons": [
    {"sme_id": "SME-01", "verdict": "same", "document_rules": ["AR-001-R3", "AR-001-R4"]},
    {"sme_id": "SME-02", "verdict": "differs", "document_rules": ["AR-001-R5"],
     "difference": "The SME says tax is 20% in region 1. The document says 18%.",
     "code_supports": "document",
     "file": "src/com/acme/ar/InvProc.java", "start_line": 28, "end_line": 29},
    {"sme_id": "SME-03", "verdict": "missing", "found_in_code": true,
     "file": "db/ar_writeoff.sql", "start_line": 24, "end_line": 24,
     "note": "A script marks customers inactive when their last invoice is more than 36 months old."},
    {"sme_id": "SME-04", "verdict": "missing", "found_in_code": false,
     "searched_for": ["credit limit", "CR_LIMIT", "block", "hold"],
     "note": "Nothing in the module folders checks a credit limit."}
  ]
}
```

Every id of the SME rules file appears exactly once. File paths are written as in the document rules file.
