# Security notes

What the daftar does today, stated plainly.

## Passwords and sessions

- Passwords are stored as PBKDF2 HMAC SHA256 hashes with a per user random salt, 140,000 iterations. The plain password never touches the database.
- Login returns a random bearer token that expires after 12 hours. Tokens live in server memory, so a restart logs everyone out. That is acceptable for one shop on one machine and wrong for a hosted multi shop service.
- Password comparison uses a constant time check.
- Failed logins, wrong tokens, and missing tokens all get the same refusal shape, and every API query is scoped to the shop on the token. One shop cannot read another shops pages through this API.

## Injection and input

- Every SQL statement uses bound parameters. A login attempt with a classic injection string in the username is tested and returns 401.
- Names, phones, notes, and descriptions are length capped on the way in. Amounts must be positive numbers, dates must be real ISO dates, and a payment larger than the customers balance is refused by the ledger rules, not by trust in the browser.
- Request bodies are size capped. The frontend escapes customer text before putting it in the page.

## Before this belongs on the public internet

- Serve it over HTTPS only. Tokens and passwords travel in the clear on plain HTTP.
- Add login rate limiting and a lockout after repeated failures. There is none today.
- Move tokens to a database table with revocation if more than one device per shop needs managing.
- Change the seeded demo password. It is printed in the README on purpose for the local demo and must never survive into a real shop.
- Back up the SQLite file on a schedule. The daftar is the shops money memory, and a lost file is the paper problem all over again.
