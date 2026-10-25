# Changelog

## 1.1.0, 2026-10-24, English conversion and the Risograph Ledger redesign

- The whole product is English only now: interface, API error messages, the WhatsApp reminder text, seed data, README and tests. Layout is LTR. The Egyptian setting stays, written in English words (El Nour Grocery, Market Street, Tanta-style neighbourhood shops).
- The interface was rebuilt as a Risograph Ledger (see DESIGN.md): two spot inks only, teal #0F6B5C and fluorescent vermillion #FF4D1C on print paper #FBF6EA, Archivo headings printed slightly off register, Space Mono for every number, date and statement line.
- The board is a ruled register instead of stat cards; customer pages are printed sheets whose tab edges stick out in alternating inks, and an over-limit customer's tab is overprinted in both inks. Over-limit entries carry a rotated vermillion stamp instead of a badge.
- Saving an entry now "prints" the line into the statement with a short multiply-blend stamp-in animation (disabled under prefers-reduced-motion).
- Backend logic and money math are unchanged. The seed still produces a board total of 10,670 EGP and the full suite still passes 16 of 16.

## 1.0.1, 2026-10-24

- Credit limit flags now follow each debt its place in the ledger. When a shopkeeper records a debt with an older date, the entry is marked only if the running balance at that point in the statement passed the limit, and the marks on the rest of the page are recalculated so the statement never disagrees with itself. Before this fix a backdated debt was judged against todays total balance.
- Added a test that locks the backdated behaviour in.

## 1.0.0, 2026-10-24

First working daftar.

- Shop login with PBKDF2 hashed passwords and bearer tokens.
- Customer pages with phone, address, a private note, and a per customer credit limit. Duplicate phones are refused.
- Debt and payment entries. Balances are always calculated from the entries, a payment bigger than the balance is refused, and a debt that passes the credit limit is recorded and marked instead of blocked.
- Printable customer statement with the running balance after every line.
- Home board with total outstanding, largest balances, over limit customers, and open debt aged 0 to 7, 8 to 30, and over 30 days. Payments settle the oldest open debt first.
- WhatsApp reminder text prepared per customer. The app never sends anything.
- Customer search by name or phone digits.
- CSV import of customers with duplicate detection and a skipped rows report, plus CSV export of the full ledger.
- Arabic RTL notebook interface: cream ruled paper, red margin line, customer pages as tabs.
- Seed data for one fictional grocery shop, 12 customers and 32 dated entries, and an automated test suite.
