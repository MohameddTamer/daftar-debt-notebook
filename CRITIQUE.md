# Critique, 2026-10-24

Self review after building. Everything below was run, not assumed.

## State found

A previous build round had already produced the backend, seed, frontend, README, and 15 tests before the owner stopped the work. This round reviewed all of it, kept it, fixed one real defect (below), added one test, and wrote the missing CHANGELOG.md and SECURITY.md. Nothing was restarted from scratch.

## Tests

16 automated tests, all passing (`python3 tests/test_daftar.py`, about 0.7s). They boot the real server on a throwaway database and cover:

- Board total equals an independent raw SQL sum over the entries table.
- Statement running balance recomputed line by line in the test itself.
- The settled seed customer ends at exactly zero.
- Overpayment refused with 400 and the balance named in the response.
- A debt over the credit limit is created, returned, and marked.
- Duplicate customer phone refused with 409.
- CSV import creates the new row and reports both an existing phone and a phone repeated inside the file as skipped duplicates.
- Aging buckets on a hand built FIFO fixture, including an uncovered old debt at 84 days.
- 401 with no token, 401 with a wrong password, 401 for a login injection string in the username.
- Search by a middle slice of phone digits finds the right customer, and he is over limit.
- Reminder text contains the customer name, the shop name, and the balance.
- Ledger export row count tracks the database.
- Backdated debt flag behaviour (the fix below).

## Live walk on the seeded demo

Server booted on port 8091 against the seeded shop and driven over HTTP:

- Frontend served 200 with the notebook styling present.
- Board without a token returned 401. Login returned 200.
- Board at 2026-10-24: total outstanding 10,670 EGP across 11 customers with a balance, over limit list holds exactly the two seeded cases, aging 1,240 in 0 to 7 days, 6,630 in 8 to 30, 2,800 over 30. The three buckets sum to the same 10,670, which cross checks the aging code against the balance code.
- Export returned 33 lines, a header plus the 32 seeded entries.
- Import of a two row file created one customer and reported the other as a duplicate phone.
- A payment of 99,999 against a 470 balance was refused.

## Hand verification

Customer one, Hassan the Grocer, by hand from the seed: 850 debt, 300 paid, 420 debt, 500 paid. 850 − 300 + 420 − 500 = 470. The API, the statement last line, and a direct SQL group by all say 470.

Shop total by hand, summing the twelve per customer balances (470, 750, 1220, 1240, 1050, 750, 930, 870, 1650, 0, 900, 840) gives 10,670, matching the seed script, raw SQL, and the board endpoint.

Flagged entries in the seed are exactly two: the second debt of Mona Abdel Rahman, where the running balance steps from 780 to 1,240 past her 1,000 limit, and the second debt of Khaled Abu Saree, 500 to 930 past his 700 limit.

## Gap found and fixed

The credit limit flag was judged against the customers total balance at the moment of entry. A debt recorded late with an older date could be marked even though the balance on its own day never crossed the limit, and the statement could then disagree with itself. Entry creation now recomputes the flags along the whole statement in date order, the same way the seed builds them, and a new test pins the behaviour: a backdated debt of 50 under a 100 limit stays unmarked while the later dated entry that actually crosses the line carries the mark.

## Honest incompletes

- The frontend was exercised through the API it calls and its markup and script were read end to end, but it was not clicked through in a live browser in this round, and it was not rendered on a physical Android or iOS device. The CSS is responsive and the print view exists in code; neither was seen on real hardware.
- There is no edit or delete for entries anywhere. A mistake needs a correcting entry today. The README says the same.
- Tokens are in memory and login has no rate limit. SECURITY.md lists what must change before any public hosting, HTTPS first.
- Money is stored as rounded SQLite reals. Fine at one shop scale, not formal accounting. Noted in the README.
- The export test compares counts with a small tolerance because earlier tests in the same suite add entries to the shared database. The live walk above gives the exact figure on a clean seed instead.

## Redesign and English conversion, 2026-10-24

The interface was rebuilt as a Risograph Ledger (two spot inks, off-register Archivo headings, Space Mono figures, printed tab edges, over-limit stamps) and everything user-facing was converted to English only: UI, API errors, the WhatsApp reminder, seed names and descriptions, README example data and the tests' own fixture names. FULL rationale lives in DESIGN.md. Backend logic and money math were not touched.

### Tests before and after

- Before the conversion: `python3 tests/test_daftar.py`, 16 tests, OK.
- After the conversion and the frontend rewrite: the same command, **16 tests, OK**. The only test edits were fixture strings (test-created customer names, the import CSV rows, and the shop name asserted inside the reminder text, now "El Nour Grocery").

### Numbers unchanged, proof

- Fresh seed after the conversion prints: `Customers: 12  Entries: 32  Shop balance: 10670.0`, the board total is still **10,670 EGP**, identical to the pre-redesign seed.
- Per-customer seed balances are untouched because only display strings changed; amounts, dates, phones and credit limits in `seed.py` are byte-identical values (470, 750, 1220, 1240, 1050, 750, 930, 870, 1650, 0, 900, 840).
- The two flagged seed entries are still Mona Abdel Rahman's second debt (running balance 780 → 1,240 over her 1,000 limit) and Khaled Abu Saree's second debt (500 → 930 over his 700 limit); the over-limit flag regression test for backdated entries still passes.

### Honest gaps in this pass

- The new frontend was verified by serving the page over HTTP and checking the markup and script by eye and by `node --check`-equivalent review; it was not clicked through in a real browser in this environment (no Chromium installed), so the print-in animation and the tab overprint have not been seen rendering live.
- Google Fonts (Archivo, Space Mono) load from the CDN; offline, the page falls back to Arial Narrow / Courier New, which keeps the structure but loses the off-register poster feel of Archivo Black-weight headings.
- The grain overlay sits on the masthead band only, by design decision (never under text); the "grain shifts when an entry prints" detail from the research note was simplified to the stamp-in animation alone.
