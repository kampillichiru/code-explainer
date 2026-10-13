# Rules for every step

You are documenting what a legacy accounting system does today. Its logic is in Java code, SQL scripts and stored procedures, and configuration files. The document will be used as the requirement document to rebuild the same logic in another system, so a wrong or invented rule is worse than a missing one. The reader is a business analyst who cannot read Java or SQL.

1. Describe only what the code does. Do not describe what it should do, and do not suggest improvements or a new design.
2. Read the real source lines before you write anything about them. Never work from a method name: names in this code are often wrong.
3. Every rule must point to the file and the lines it comes from.
4. If you are not sure what something means, do not guess. Set the rule status to `unclear` and write a question for the business expert (SME).
5. If the code looks like a bug, still document what it does, and add a question for the SME.
6. Write in simple English. Short sentences. No Java words in the rule text (no "method", "null", "boolean"). Say "the customer is not found", not "c == null".
7. Use business names. When a name in the code is unclear (for example `calcAmt2`, `exFlg`), work out its meaning from how it is used and add it to the glossary.
8. Keep exact values, with their unit: rates (18%), limits, number of days (5 days), rounding (2 decimals), status codes, table and column names.
9. Do not change any source file (Java, SQL or configuration). Write only the output file named in the step.
10. The tool `explain.py` is in the `scripts` folder, next to this `steps` folder. Run it with Python from the `scripts` folder.
11. No value without an origin. For every value a rule uses or produces, say where it comes from: given as input, read from the database (table and column), fixed in the code (the exact value), calculated (the formula), returned by another module, set in a configuration file (the setting name with its value), or taken from the system (for example today's date).
12. The code shows what happens; it seldom shows why. Give the business reason for every rule and every flow, and always say how you know it:
    - `stated`: a code comment, a message text, or the notes of the business team says it. Name which one.
    - `inferred`: you worked it out from what the code does. The document marks it "to be confirmed by the SME".
    - `unknown`: the code gives no hint. Write "Not known from the code" and add a question for the SME. Never fill the gap with a likely-sounding reason.
13. SQL scripts and stored procedures hold business logic too. Explain which records are chosen (the conditions), what is calculated, and which tables and columns are changed. A condition in a WHERE clause is a business condition.
14. Configuration files: a setting that changes a business result is business logic. Examples: a rate, a limit, a number of days, a switch that turns a behaviour on or off, a schedule. Write its name and its exact value. Settings that only make the system run (connection, pool size, logging, file paths) are technical: list them under `no_business_rule`.
15. Never copy a password, key or token into any output file. Write "(secret, not shown)".
