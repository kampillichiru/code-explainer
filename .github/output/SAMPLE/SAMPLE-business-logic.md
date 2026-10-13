# SAMPLE - Business logic of the current system

This document describes what the current system does. It was produced from the source code.

How to read it: this page is the summary. Chapter 2 lists each feature with its functional requirements. The title of a feature is a link to its own page, with the business rules, the flow diagram, the scenarios and the worked examples. Every id (**FR** = functional requirement, **BR** = business rule, **SC** = scenario) is a link. Appendix A links every requirement to its rule and to the lines of code.

Status marks: **Code-checked** = passed the automatic checks. **Second check** = a second, independent review agreed. **SME confirmed** = to be ticked by the business expert.

## 1. Module overview

Not written yet. It is written when all features are documented.

| | Number |
|---|---|
| Features | 4 |
| Functional requirements | 17 |
| Business rules | 13 |
| Scenarios (ways through a feature, from start to end) | 11 |
| Open questions for the SME | 18 |

## 2. Features

| Feature | Requirements | Rules | Scenarios | Open questions | Not yet second-checked |
|---|---|---|---|---|---|
| [2.1 Amount owed on an invoice](features/01-amount-owed-on-an-invoice.md) | 8 | 5 | 3 | 4 | 1 |
| [2.2 Old posting check for negative amounts](features/02-old-posting-check-for-negative-amounts.md) | 0 | 0 | 1 | 1 | 1 |
| [2.3 Statement day and reminder letter settings](features/03-statement-day-and-reminder-letter-settings.md) | 4 | 4 | 3 | 5 | 1 |
| [2.4 Write off small balances and deactivate dormant customers](features/04-write-off-small-balances-and-deactivate-dormant-cu.md) | 5 | 4 | 4 | 7 | 1 |

### [2.1 Amount owed on an invoice](features/01-amount-owed-on-an-invoice.md)

Works out the total a customer owes on one invoice. It adds late payment interest when the invoice is paid late enough, then adds regional tax, and rounds the total to 2 decimals. It rejects unknown or inactive customers.

- **[FR-01](features/01-amount-owed-on-an-invoice.md#FR-01):** The system shall reject an invoice request with the message "no customer" when no customer with status 'A' is found. ([BR-01](features/01-amount-owed-on-an-invoice.md#BR-01))
- **[FR-02](features/01-amount-owed-on-an-invoice.md#FR-02):** The system shall treat a failed customer lookup in the same way as a customer that is not found. ([BR-01](features/01-amount-owed-on-an-invoice.md#BR-01))
- **[FR-03](features/01-amount-owed-on-an-invoice.md#FR-03):** The system shall count the days late as whole days from the due date to the processing date, and as 0 days when the processing date is not after the due date. ([BR-02](features/01-amount-owed-on-an-invoice.md#BR-02))
- **[FR-04](features/01-amount-owed-on-an-invoice.md#FR-04):** The system shall allow 15 free days for customers of type 'G' and 5 free days for all other customers. ([BR-03](features/01-amount-owed-on-an-invoice.md#BR-03))
- **[FR-05](features/01-amount-owed-on-an-invoice.md#FR-05):** The system shall add late payment interest only when the days late are more than the free days and the customer is not marked exempt. ([BR-03](features/01-amount-owed-on-an-invoice.md#BR-03))
- **[FR-06](features/01-amount-owed-on-an-invoice.md#FR-06):** The system shall calculate late payment interest as the invoice amount x the customer's yearly rate / 365 x days late. ([BR-04](features/01-amount-owed-on-an-invoice.md#BR-04))
- **[FR-07](features/01-amount-owed-on-an-invoice.md#FR-07):** The system shall add regional tax of 18% of the invoice amount for region 1, 5% for region 2, and none for any other region. ([BR-05](features/01-amount-owed-on-an-invoice.md#BR-05))
- **[FR-08](features/01-amount-owed-on-an-invoice.md#FR-08):** The system shall round the total owed to 2 decimals, with halves rounded up. ([BR-05](features/01-amount-owed-on-an-invoice.md#BR-05))

### [2.2 Old posting check for negative amounts](features/02-old-posting-check-for-negative-amounts.md)

An old routine receives an amount and writes the text "neg" to the console when the amount is below zero. It changes no amount, saves nothing and returns nothing. No other code in this module calls it.

> Note: no other code in this module calls this code. Confirm if it is still used.

No business behaviour.

### [2.3 Statement day and reminder letter settings](features/03-statement-day-and-reminder-letter-settings.md)

Settings fix the day of the month for customer statements and control reminder letters: whether they are sent, the smallest balance that gets one, and the days late at which letters go out.

- **[FR-09](features/03-statement-day-and-reminder-letter-settings.md#FR-09):** The system shall produce customer statements on day 5 of each month. ([BR-06](features/03-statement-day-and-reminder-letter-settings.md#BR-06))
- **[FR-10](features/03-statement-day-and-reminder-letter-settings.md#FR-10):** The system shall send reminder letters only when the reminder letter switch is on. ([BR-07](features/03-statement-day-and-reminder-letter-settings.md#BR-07))
- **[FR-11](features/03-statement-day-and-reminder-letter-settings.md#FR-11):** The system shall not send a reminder letter for a balance below 25.00. ([BR-08](features/03-statement-day-and-reminder-letter-settings.md#BR-08))
- **[FR-12](features/03-statement-day-and-reminder-letter-settings.md#FR-12):** The system shall send reminder letters at 30, 60 and 90 days late. ([BR-09](features/03-statement-day-and-reminder-letter-settings.md#BR-09))

### [2.4 Write off small balances and deactivate dormant customers](features/04-write-off-small-balances-and-deactivate-dormant-cu.md)

A nightly run writes off small, long-overdue open invoices, but stops and undoes everything if more than 1,000 would be written off. A separate script marks customers inactive when they have had no invoice for 36 months.

- **[FR-13](features/04-write-off-small-balances-and-deactivate-dormant-cu.md#FR-13):** The system shall write off an open invoice when its balance is above 0 and at most 2.50 and its due date is more than 90 days before the run date. ([BR-10](features/04-write-off-small-balances-and-deactivate-dormant-cu.md#BR-10))
- **[FR-14](features/04-write-off-small-balances-and-deactivate-dormant-cu.md#FR-14):** The system shall mark a written-off invoice with status W and the run date as its write-off date. ([BR-10](features/04-write-off-small-balances-and-deactivate-dormant-cu.md#BR-10))
- **[FR-15](features/04-write-off-small-balances-and-deactivate-dormant-cu.md#FR-15):** The system shall undo all write-offs of a run and raise the error 'too many write-offs' when more than 1,000 invoices would be written off. ([BR-11](features/04-write-off-small-balances-and-deactivate-dormant-cu.md#BR-11))
- **[FR-16](features/04-write-off-small-balances-and-deactivate-dormant-cu.md#FR-16):** The system shall undo all write-offs of a run and pass the error on to the caller when any error occurs during the write-off. ([BR-12](features/04-write-off-small-balances-and-deactivate-dormant-cu.md#BR-12))
- **[FR-17](features/04-write-off-small-balances-and-deactivate-dormant-cu.md#FR-17):** The system shall mark an active customer as inactive when the customer's last invoice date is more than 36 months before today. ([BR-13](features/04-write-off-small-balances-and-deactivate-dormant-cu.md#BR-13))

## 3. Glossary: names in the code and their business meaning

| Name in code | Business meaning |
|---|---|
| `AR_INVOICE.STS` | Invoice status: O = open, W = written off |
| `BAL_AMT` | Balance still owed on the invoice |
| `CUST_MASTER.STS` | Customer status: A = active, I = inactive |
| `DUE_DT` | Invoice due date |
| `LAST_INV_DT` | Date of the customer's last invoice |
| `STS` | Customer status; 'A' means active |
| `WRITEOFF_DT` | Date the invoice was written off |
| `ar.dunning.letter.after.days` | Days late at which each reminder letter is sent |
| `ar.dunning.min.balance` | Smallest balance that gets a reminder letter |
| `calcAmt2` | Late payment interest amount |
| `dunning` | Reminder letters sent to customers who have not paid |
| `exFlg / EXEMPT_FLG` | Customer is exempt from late payment interest |
| `oldPost` | Old routine that reports a negative amount on the console; its name suggests posting, but it posts nothing |
| `procA` | Work out the total owed on an invoice |
| `reg / REG` | Customer's tax region code |
| `rt / RT` | Customer's yearly interest rate |
| `tx` | Regional tax amount |
| `typ / TYP` | Customer type; 'G' gets longer free days |

## 4. Fixed business values

Values that are written in the code itself. To change one of them today, the code must be changed.

| Value | Fixed at | Used in rule |
|---|---|---|
| Milliseconds in a day | 86400000 | [BR-02](features/01-amount-owed-on-an-invoice.md#BR-02) |
| Free days, type 'G' | 15 | [BR-03](features/01-amount-owed-on-an-invoice.md#BR-03) |
| Free days, other types | 5 | [BR-03](features/01-amount-owed-on-an-invoice.md#BR-03) |
| Days in a year | 365 | [BR-04](features/01-amount-owed-on-an-invoice.md#BR-04) |
| Tax rate, region 1 | 0.18 | [BR-05](features/01-amount-owed-on-an-invoice.md#BR-05) |
| Tax rate, region 2 | 0.05 | [BR-05](features/01-amount-owed-on-an-invoice.md#BR-05) |
| Tax rate, other regions | 0 | [BR-05](features/01-amount-owed-on-an-invoice.md#BR-05) |
| Write-off limit | 2.50 | [BR-10](features/04-write-off-small-balances-and-deactivate-dormant-cu.md#BR-10) |
| Days overdue before write-off | 90 | [BR-10](features/04-write-off-small-balances-and-deactivate-dormant-cu.md#BR-10) |
| Written-off status | 'W' stored in AR_INVOICE.STS | [BR-10](features/04-write-off-small-balances-and-deactivate-dormant-cu.md#BR-10) |
| Maximum write-offs per run | 1000 | [BR-11](features/04-write-off-small-balances-and-deactivate-dormant-cu.md#BR-11) |
| Error number | -20001 | [BR-11](features/04-write-off-small-balances-and-deactivate-dormant-cu.md#BR-11) |
| Error text | too many write-offs | [BR-11](features/04-write-off-small-balances-and-deactivate-dormant-cu.md#BR-11) |
| Months without invoice | 36 | [BR-13](features/04-write-off-small-balances-and-deactivate-dormant-cu.md#BR-13) |
| Active / inactive codes | 'A' / 'I' | [BR-13](features/04-write-off-small-balances-and-deactivate-dormant-cu.md#BR-13) |

## 5. Open questions for the SME

- Users and roles: the code does not show who uses these features or what each role is allowed to do. Please say it for: 2.1 Amount owed on an invoice; 2.2 Old posting check for negative amounts; 2.3 Statement day and reminder letter settings; 2.4 Write off small balances and deactivate dormant customers.
- Amount owed on an invoice: Who or what starts this calculation: a user screen, a batch job or another system?
- BR-01: Is it right that a database failure is reported as 'no customer', or should it be a separate error?
- BR-04: Is the yearly rate stored as a decimal (0.12 for 12%)? The code uses it as is, without dividing by 100.
- BR-05: What do region codes 1 and 2 stand for, and should other regions really pay no tax?
- Old posting check for negative amounts: Is the old posting routine still used, and what should happen to a negative amount?
- Statement day and reminder letter settings: Which program reads these settings? No code in this module uses them, so how they are applied is not shown.
- BR-06: What happens when day 5 is a weekend or holiday? Is the statement run moved?
- BR-07: Why can letters be switched off, and who decides? No code in this module reads the switch.
- BR-08: Is a balance of exactly 25.00 sent a letter? What currency is the limit in, and is it per invoice or per customer?
- BR-09: Are the days counted from the invoice date or the due date? Is the wording of each letter different?
- Write off small balances and deactivate dormant customers: Who or what starts the nightly write-off and the customer script, and at what time?
- Write off small balances and deactivate dormant customers: Is the customer script meant to be part of the nightly run, and is its result saved afterwards?
- BR-10: What currency is the 2.50 limit in, and is it right for every customer and region?
- BR-10: Should the 90 days count from the due date as the code does, or from the invoice date?
- BR-11: Why is the cap 1,000, and what should happen when it is exceeded: who is told and how are the invoices handled afterwards?
- BR-13: Is deactivating dormant customers intended, and why 36 months? The change is not saved by this script: who saves it?
- BR-13: Should customers with no last invoice date also be deactivated?

## Appendix A. From each requirement to its rule, its scenarios and the code

| Rule | Needed by | Used in scenarios | Code lines |
|---|---|---|---|
| <a id="trace-BR-01"></a>[BR-01](features/01-amount-owed-on-an-invoice.md#BR-01) | [FR-01](features/01-amount-owed-on-an-invoice.md#FR-01), [FR-02](features/01-amount-owed-on-an-invoice.md#FR-02) | [SC-01](features/01-amount-owed-on-an-invoice.md#SC-01), [SC-02](features/01-amount-owed-on-an-invoice.md#SC-02), [SC-03](features/01-amount-owed-on-an-invoice.md#SC-03) | `sample/src/com/acme/ar/CustDao.java` lines 8-26; `sample/src/com/acme/ar/InvProc.java` lines 12-15 |
| <a id="trace-BR-02"></a>[BR-02](features/01-amount-owed-on-an-invoice.md#BR-02) | [FR-03](features/01-amount-owed-on-an-invoice.md#FR-03) | [SC-01](features/01-amount-owed-on-an-invoice.md#SC-01), [SC-02](features/01-amount-owed-on-an-invoice.md#SC-02) | `sample/src/com/acme/ar/Util.java` lines 6-9 |
| <a id="trace-BR-03"></a>[BR-03](features/01-amount-owed-on-an-invoice.md#BR-03) | [FR-04](features/01-amount-owed-on-an-invoice.md#FR-04), [FR-05](features/01-amount-owed-on-an-invoice.md#FR-05) | [SC-01](features/01-amount-owed-on-an-invoice.md#SC-01), [SC-02](features/01-amount-owed-on-an-invoice.md#SC-02) | `sample/src/com/acme/ar/InvProc.java` lines 18-21 |
| <a id="trace-BR-04"></a>[BR-04](features/01-amount-owed-on-an-invoice.md#BR-04) | [FR-06](features/01-amount-owed-on-an-invoice.md#FR-06) | [SC-01](features/01-amount-owed-on-an-invoice.md#SC-01) | `sample/src/com/acme/ar/Calc2.java` lines 6-9; `sample/src/com/acme/ar/InvProc.java` lines 20-20 |
| <a id="trace-BR-05"></a>[BR-05](features/01-amount-owed-on-an-invoice.md#BR-05) | [FR-07](features/01-amount-owed-on-an-invoice.md#FR-07), [FR-08](features/01-amount-owed-on-an-invoice.md#FR-08) | [SC-01](features/01-amount-owed-on-an-invoice.md#SC-01), [SC-02](features/01-amount-owed-on-an-invoice.md#SC-02) | `sample/src/com/acme/ar/InvProc.java` lines 22-23; `sample/src/com/acme/ar/InvProc.java` lines 26-35 |
| <a id="trace-BR-06"></a>[BR-06](features/03-statement-day-and-reminder-letter-settings.md#BR-06) | [FR-09](features/03-statement-day-and-reminder-letter-settings.md#FR-09) | [SC-05](features/03-statement-day-and-reminder-letter-settings.md#SC-05), [SC-06](features/03-statement-day-and-reminder-letter-settings.md#SC-06), [SC-07](features/03-statement-day-and-reminder-letter-settings.md#SC-07) | `sample/config/ar.properties` lines 2-2 |
| <a id="trace-BR-07"></a>[BR-07](features/03-statement-day-and-reminder-letter-settings.md#BR-07) | [FR-10](features/03-statement-day-and-reminder-letter-settings.md#FR-10) | [SC-05](features/03-statement-day-and-reminder-letter-settings.md#SC-05), [SC-06](features/03-statement-day-and-reminder-letter-settings.md#SC-06), [SC-07](features/03-statement-day-and-reminder-letter-settings.md#SC-07) | `sample/config/ar.properties` lines 3-3 |
| <a id="trace-BR-08"></a>[BR-08](features/03-statement-day-and-reminder-letter-settings.md#BR-08) | [FR-11](features/03-statement-day-and-reminder-letter-settings.md#FR-11) | [SC-05](features/03-statement-day-and-reminder-letter-settings.md#SC-05), [SC-07](features/03-statement-day-and-reminder-letter-settings.md#SC-07) | `sample/config/ar.properties` lines 4-4 |
| <a id="trace-BR-09"></a>[BR-09](features/03-statement-day-and-reminder-letter-settings.md#BR-09) | [FR-12](features/03-statement-day-and-reminder-letter-settings.md#FR-12) | [SC-05](features/03-statement-day-and-reminder-letter-settings.md#SC-05) | `sample/config/ar.properties` lines 5-5 |
| <a id="trace-BR-10"></a>[BR-10](features/04-write-off-small-balances-and-deactivate-dormant-cu.md#BR-10) | [FR-13](features/04-write-off-small-balances-and-deactivate-dormant-cu.md#FR-13), [FR-14](features/04-write-off-small-balances-and-deactivate-dormant-cu.md#FR-14) | [SC-08](features/04-write-off-small-balances-and-deactivate-dormant-cu.md#SC-08), [SC-09](features/04-write-off-small-balances-and-deactivate-dormant-cu.md#SC-09), [SC-10](features/04-write-off-small-balances-and-deactivate-dormant-cu.md#SC-10) | `sample/db/ar_writeoff.sql` lines 2-10 |
| <a id="trace-BR-11"></a>[BR-11](features/04-write-off-small-balances-and-deactivate-dormant-cu.md#BR-11) | [FR-15](features/04-write-off-small-balances-and-deactivate-dormant-cu.md#FR-15) | [SC-08](features/04-write-off-small-balances-and-deactivate-dormant-cu.md#SC-08), [SC-09](features/04-write-off-small-balances-and-deactivate-dormant-cu.md#SC-09) | `sample/db/ar_writeoff.sql` lines 12-16 |
| <a id="trace-BR-12"></a>[BR-12](features/04-write-off-small-balances-and-deactivate-dormant-cu.md#BR-12) | [FR-16](features/04-write-off-small-balances-and-deactivate-dormant-cu.md#FR-16) | [SC-08](features/04-write-off-small-balances-and-deactivate-dormant-cu.md#SC-08), [SC-09](features/04-write-off-small-balances-and-deactivate-dormant-cu.md#SC-09), [SC-10](features/04-write-off-small-balances-and-deactivate-dormant-cu.md#SC-10) | `sample/db/ar_writeoff.sql` lines 17-20 |
| <a id="trace-BR-13"></a>[BR-13](features/04-write-off-small-balances-and-deactivate-dormant-cu.md#BR-13) | [FR-17](features/04-write-off-small-balances-and-deactivate-dormant-cu.md#FR-17) | [SC-11](features/04-write-off-small-balances-and-deactivate-dormant-cu.md#SC-11) | `sample/db/ar_writeoff.sql` lines 24-24 |

| Feature | Work item | Entry point in the code |
|---|---|---|
| [2.1 Amount owed on an invoice](features/01-amount-owed-on-an-invoice.md) | SAMPLE-001 | `InvProc.procA` (`sample/src/com/acme/ar/InvProc.java` lines 11-24) |
| [2.2 Old posting check for negative amounts](features/02-old-posting-check-for-negative-amounts.md) | SAMPLE-002 | `InvProc.oldPost` (`sample/src/com/acme/ar/InvProc.java` lines 37-41) |
| [2.3 Statement day and reminder letter settings](features/03-statement-day-and-reminder-letter-settings.md) | SAMPLE-003 | `(settings)` (`sample/config/ar.properties` lines 1-11) |
| [2.4 Write off small balances and deactivate dormant customers](features/04-write-off-small-balances-and-deactivate-dormant-cu.md) | SAMPLE-004 | `PROCEDURE ar_writeoff_small` (`sample/db/ar_writeoff.sql` lines 2-22); `(script)` (`sample/db/ar_writeoff.sql` lines 23-24) |
