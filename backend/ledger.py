from datetime import date


def parse_day(value):
    return date.fromisoformat(value)


def balance_of(entries):
    total = 0.0
    for entry in entries:
        amount = float(entry["amount"])
        if entry["kind"] == "debt":
            total += amount
        elif entry["kind"] == "payment":
            total -= amount
    return round(total, 2)


def statement_rows(entries):
    rows = []
    running = 0.0
    for entry in entries:
        amount = float(entry["amount"])
        running += amount if entry["kind"] == "debt" else -amount
        row = dict(entry)
        row["running_balance"] = round(running, 2)
        rows.append(row)
    return rows


def aging_buckets(entries, as_of):
    debts = []
    paid = 0.0
    for entry in entries:
        if entry["kind"] == "debt":
            debts.append({"entry_id": entry["id"], "day": entry["entry_date"], "left": float(entry["amount"])})
        else:
            paid += float(entry["amount"])

    # Payments settle the oldest paper first. That is how a shopkeeper reads the daftar.
    for debt in debts:
        covered = min(debt["left"], paid)
        debt["left"] = round(debt["left"] - covered, 2)
        paid = round(paid - covered, 2)
        if paid <= 0:
            paid = 0.0

    buckets = {"0-7": 0.0, "8-30": 0.0, "30+": 0.0}
    detail = []
    for debt in debts:
        if debt["left"] <= 0:
            continue
        age = (parse_day(as_of) - parse_day(debt["day"])).days
        if age <= 7:
            key = "0-7"
        elif age <= 30:
            key = "8-30"
        else:
            key = "30+"
        buckets[key] = round(buckets[key] + debt["left"], 2)
        detail.append({**debt, "age_days": age, "bucket": key})
    return {"buckets": buckets, "open_debts": detail}
