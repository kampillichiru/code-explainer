# 2.2 Old posting check for negative amounts

Part of [SAMPLE - business logic](../SAMPLE-business-logic.md). Every id on this page is a link.

> **DRAFT - NOT READY TO USE AS REQUIREMENTS.** This feature has not passed the second check (state: EXTRACTED). It may be wrong.

> Note: no other code in this module calls this code. Confirm if it is still used.

## Overview

An old routine receives an amount and writes the text "neg" to the console when the amount is below zero. It changes no amount, saves nothing and returns nothing. No other code in this module calls it.

**Why it exists:** Not known from the code

**Starts when:** Never in this module: no other code calls it.

## Business behaviour

None. This code changes no business result.

- Technical: only decides whether to write "neg" to the console. No amount, status or record changes.

## Open questions

- Old posting check for negative amounts: Is the old posting routine still used, and what should happen to a negative amount?
