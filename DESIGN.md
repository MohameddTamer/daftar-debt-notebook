# Daftar — Design Notes

## Concept: the Risograph Ledger

A daftar is a printed object before it is software. The shopkeeper's notebook lives on a counter, gets stamped, thumbed and re-ruled. The redesign treats the screen the way a risograph press treats paper: two spot inks, visible registration, honest rules and lines, and numbers set like they were struck by a machine. Nothing here pretends to be glass, plastic or a dashboard. It is a printed ledger that happens to compute.

## Palette — exactly two inks

| Role | Hex | Use |
| --- | --- | --- |
| Print paper | `#FBF6EA` | Page background, a warm uncoated stock |
| Sheet paper | `#FFFDF6` | Customer sheets, forms, the register |
| Ink 1 — teal | `#0F6B5C` | The record ink: headings, rules, structure, primary actions |
| Ink 2 — fluorescent vermillion | `#FF4D1C` | The attention ink: running balances, over-limit marks, the print action |

Where the two inks overlap with `mix-blend-mode: multiply`, an overprint third tone appears — that is the whole colour system. There is no third colour, no grey scale, no gradient anywhere. Body ink is a near-black green `#22302B` derived from the teal.

## Type

- **Archivo** (weights 500/700/900) for headings and interface text — a grotesque with a printed-poster bluntness. Fallbacks: Arial Narrow, Arial.
- **Space Mono** (400/700) for every balance, date, amount and statement line. Fallback: Courier New. All numerals are tabular; money columns never jitter when a digit changes.

Headings are printed **off register**: the teal letterform carries a 1.5px vermillion ghost offset, like a riso drum that landed a fraction late. Misregistration is allowed on headings only — body text and numbers are always perfectly registered, because a ledger you cannot read is a failed print job.

## Signature moves

- **The board is a ruled register**, not a row of stat cards: one bordered register with ruled cells for total outstanding, customers owing, over-limit count, and an aging strip ruled into 0–7 / 8–30 / 30+ days.
- **Customer sheets have printed tab edges.** Tabs stick out on the side in alternating inks. An over-limit customer's tab is overprinted in *both* inks, so the problem is visible from the board before you open the sheet.
- **The statement is one continuous ruled sheet.** Running balances print in the second ink at every line; an entry that crossed the credit limit carries a small rotated vermillion `OVER LIMIT` stamp instead of a software badge.
- **Adding an entry prints it.** The new line stamps into the statement with a short multiply-blend animation and the grain of the press band shifts — then it is still. The animation is disabled under `prefers-reduced-motion`.
- **Registration marks** sit in the masthead: two circles, teal and vermillion, deliberately overlapping in multiply — the pressman's mark as brand detail.
- **The brand mark** is a drawn ledger: a ruled book with a vermillion spine line and three ruled entries, two teal, one vermillion.

## Grain, honestly placed

A subtle SVG `feTurbulence` grain lives only on the masthead press band at 5% opacity. It never sits under body text or numbers — a ledger's figures stay clean.

## Deliberate avoidances

- No stat-card row, no pill badges, no rounded-everything surfaces: corners are square, like cut paper.
- No emoji icons, no stock illustration, no decorative gradients, no glass effects.
- No unstyled native controls: date, search, file, select and number inputs are all drawn in the two inks, including the file-picker button and the select chevron.
- No third ink "just for links" or "just for success" — success is the record ink doing its job; attention is vermillion, always meaning the same thing.
- Handwriting fonts: none. A printed ledger is type, not handwriting; the human warmth comes from the print process, not from a script face.
