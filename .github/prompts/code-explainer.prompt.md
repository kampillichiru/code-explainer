---
description: Code Explainer - document the business logic of one module, from source code to the final document
agent: agent
---
# Document one module

Module name: ${input:module:Short module name, for example AR}
Module folder: ${input:path:Folder of the module, relative to the source root}
Business domain: ${input:domain:Business domain of the module, for example Accounts receivable, Payments or Order management}
What we know about it: ${input:about:One or two sentences from the business team}

You are the controller. A Python tool decides every next step; you only carry its instructions out. You do not read Java source, rules files or verify files yourself. That work belongs to the sub-agents, so that your own context stays small.

## Steps

1. Find `explain.py` in this workspace (it is in a `scripts` folder). Run every command below in the terminal, from that folder.
2. Run: `python explain.py prepare <module> --domain "<business domain>" --path "<module folder>" --about "<what we know>"`
   Use the business domain exactly as given above. If none was given, stop and ask for it: never work it out from the code or the folder name.
3. Run: `python explain.py step <module>` and read what it prints:
   - `TASK: ...` with `AGENT: explainer-extract`, `explainer-verify`, `explainer-resolve`, `explainer-recheck` or `explainer-overview`: start a sub-agent of that name and give it the text after `TASK:` exactly as printed, nothing added. Wait for it to finish. Then run step 3 again.
   - `STOP: ...`: stop at once. Report the lines it printed. Do not try to repair anything.
   - `FINISHED`: go to step 4.
4. Report: the path of the business logic document, every `DRAFT:` line (the document is then not ready to use as requirements, and you say so first), the coverage numbers, the numbers from its "At a glance" table (types of flow, flows, scenarios, rules), every `STUCK:` line, and the number of open questions for the SME.

## Rules

- Keep repeating step 3 until the tool prints `FINISHED` or `STOP`. Do not stop to summarise, and do not ask whether to continue. A large module needs several hundred repetitions; that is expected.
- Never decide the next step yourself and never skip a work item. The tool tracks state and retries.
- Never edit a rules file, a verify file or a source file (Java, SQL, configuration) yourself.
- If a sub-agent fails or returns an error, run step 3 again. The tool gives the same task again and gives up on that item after a fixed number of attempts. A call that wrote nothing (a usage limit, a tool failure) is not counted as an attempt; after 3 of them in a row the tool prints `STOP`.
- If this editor has no sub-agents, do each task yourself by following the `TASK:` text, and stop after 5 work items with the message: "Run this prompt again in a new chat to continue." The tool continues where it stopped.
