#!/usr/bin/env python3
import csv
import hashlib
import hmac
import io
import json
import os
import re
import secrets
import sqlite3
import time
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from ledger import aging_buckets, balance_of, statement_rows

BASE = os.path.dirname(__file__)
DB_PATH = os.environ.get("DAFTAR_DB", os.path.join(BASE, "daftar.db"))
FRONTEND = os.path.join(BASE, "..", "frontend", "index.html")
TOKENS = {}
TOKEN_TTL = 12 * 3600


def connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def make_hash(password, salt):
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 140_000).hex()


def password_ok(password, salt_hex, expected):
    got = make_hash(password, bytes.fromhex(salt_hex))
    return hmac.compare_digest(got, expected)


def clean_phone(value):
    return re.sub(r"\D", "", str(value or ""))


def valid_day(value):
    try:
        date.fromisoformat(str(value))
        return True
    except ValueError:
        return False


def money(value):
    return round(float(value) + 0.0, 2)


def entry_dict(row):
    data = dict(row)
    data["amount"] = float(data["amount"])
    data["flagged"] = bool(data["flagged"])
    return data


def customer_entries(conn, shop_id, customer_id):
    rows = conn.execute(
        """SELECT * FROM entries WHERE shop_id = ? AND customer_id = ?
           ORDER BY entry_date, id""",
        (shop_id, customer_id),
    ).fetchall()
    return [entry_dict(row) for row in rows]


def customer_payload(conn, shop_id, row):
    data = dict(row)
    entries = customer_entries(conn, shop_id, data["id"])
    data["balance"] = balance_of(entries)
    data["credit_limit"] = float(data["credit_limit"])
    data["over_limit"] = data["credit_limit"] > 0 and data["balance"] > data["credit_limit"]
    data["entries_count"] = len(entries)
    return data


class DaftarHandler(BaseHTTPRequestHandler):
    server_version = "Daftar/1.0"

    def send_json(self, status, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def send_text(self, status, text, content_type, filename=None):
        body = text.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        if filename:
            self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.end_headers()
        self.wfile.write(body)

    def read_body(self, limit=1_000_000):
        length = int(self.headers.get("Content-Length") or 0)
        if length > limit:
            return None
        return self.rfile.read(length)

    def read_json(self):
        raw = self.read_body()
        if raw is None:
            return None
        try:
            return json.loads(raw.decode("utf-8") or "{}")
        except (UnicodeDecodeError, json.JSONDecodeError):
            return None

    def session(self):
        token = (self.headers.get("Authorization") or "").removeprefix("Bearer ").strip()
        found = TOKENS.get(token)
        if not found or found["expires"] < time.time():
            return None
        return found

    def need_session(self):
        found = self.session()
        if not found:
            self.send_json(401, {"error": "Sign in first"})
            return None
        return found

    def customer_or_404(self, conn, shop_id, customer_id):
        row = conn.execute(
            "SELECT * FROM customers WHERE shop_id = ? AND id = ?", (shop_id, customer_id)
        ).fetchone()
        if not row:
            self.send_json(404, {"error": "Customer not found"})
            return None
        return row

    def do_POST(self):
        path = urlparse(self.path).path
        if path == "/api/login":
            data = self.read_json()
            if data is None:
                return self.send_json(400, {"error": "Invalid data"})
            username = str(data.get("username", "")).strip()[:50]
            password = str(data.get("password", ""))[:120]
            conn = connect()
            row = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
            shop = None
            if row:
                shop = conn.execute("SELECT * FROM shops WHERE id = ?", (row["shop_id"],)).fetchone()
            conn.close()
            if not row or not shop or not password_ok(password, row["salt"], row["pw_hash"]):
                return self.send_json(401, {"error": "Username or password is incorrect"})
            token = secrets.token_urlsafe(32)
            TOKENS[token] = {
                "user_id": row["id"],
                "shop_id": row["shop_id"],
                "username": row["username"],
                "expires": time.time() + TOKEN_TTL,
            }
            return self.send_json(200, {"token": token, "shop": dict(shop), "username": row["username"]})

        session = self.need_session()
        if not session:
            return
        shop_id = session["shop_id"]

        if path == "/api/customers":
            data = self.read_json()
            if data is None:
                return self.send_json(400, {"error": "Invalid data"})
            name = str(data.get("name", "")).strip()[:100]
            phone = clean_phone(data.get("phone"))[:20]
            address = str(data.get("address", "")).strip()[:200]
            note = str(data.get("note", "")).strip()[:300]
            try:
                limit = money(data.get("credit_limit", 0))
            except (TypeError, ValueError):
                return self.send_json(400, {"error": "Invalid credit limit"})
            if not name or limit < 0:
                return self.send_json(400, {"error": "Customer name is required and the credit limit cannot be negative"})
            conn = connect()
            if phone:
                exists = conn.execute(
                    "SELECT id FROM customers WHERE shop_id = ? AND phone = ?", (shop_id, phone)
                ).fetchone()
                if exists:
                    conn.close()
                    return self.send_json(409, {"error": "This phone number is registered to another customer"})
            try:
                cur = conn.execute(
                    """INSERT INTO customers (shop_id, name, phone, address, note, credit_limit)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (shop_id, name, phone, address, note, limit),
                )
                conn.commit()
                row = conn.execute("SELECT * FROM customers WHERE id = ?", (cur.lastrowid,)).fetchone()
                payload = customer_payload(conn, shop_id, row)
            finally:
                conn.close()
            return self.send_json(201, {"customer": payload})

        if path == "/api/customers/import":
            raw = self.read_body()
            if raw is None:
                return self.send_json(413, {"error": "File is larger than allowed"})
            try:
                text = raw.decode("utf-8-sig")
                reader = csv.DictReader(io.StringIO(text))
            except UnicodeDecodeError:
                return self.send_json(400, {"error": "The file is not a valid CSV"})
            needed = {"name", "phone"}
            if not reader.fieldnames or not needed.issubset({h.strip() for h in reader.fieldnames}):
                return self.send_json(400, {"error": "The CSV must include name and phone columns"})
            conn = connect()
            existing = {
                row["phone"]
                for row in conn.execute("SELECT phone FROM customers WHERE shop_id = ? AND phone <> ''", (shop_id,))
            }
            seen = set(existing)
            created = []
            skipped = []
            for number, raw_row in enumerate(reader, start=2):
                row = {(key or "").strip(): (value or "").strip() for key, value in raw_row.items()}
                name = row.get("name", "")[:100]
                phone = clean_phone(row.get("phone"))[:20]
                if not name:
                    skipped.append({"row": number, "phone": phone, "reason": "missing name"})
                    continue
                if phone and phone in seen:
                    skipped.append({"row": number, "phone": phone, "reason": "duplicate phone"})
                    continue
                try:
                    limit = money(row.get("credit_limit") or 0)
                    if limit < 0:
                        raise ValueError
                except ValueError:
                    skipped.append({"row": number, "phone": phone, "reason": "invalid credit limit"})
                    continue
                cur = conn.execute(
                    """INSERT INTO customers (shop_id, name, phone, address, note, credit_limit)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (shop_id, name, phone, row.get("address", "")[:200], row.get("note", "")[:300], limit),
                )
                if phone:
                    seen.add(phone)
                created.append(cur.lastrowid)
            conn.commit()
            conn.close()
            return self.send_json(201, {"created": len(created), "customer_ids": created, "skipped": skipped})

        match = re.fullmatch(r"/api/customers/(\d+)/entries", path)
        if match:
            customer_id = int(match.group(1))
            data = self.read_json()
            if data is None:
                return self.send_json(400, {"error": "Invalid data"})
            kind = str(data.get("kind", "")).strip()
            day = str(data.get("entry_date", "")).strip()
            description = str(data.get("description", "")).strip()[:250]
            try:
                amount = money(data.get("amount"))
            except (TypeError, ValueError):
                return self.send_json(400, {"error": "Invalid amount"})
            if kind not in ("debt", "payment") or not valid_day(day) or amount <= 0:
                return self.send_json(400, {"error": "Entry kind, date and amount must all be valid"})
            if kind == "debt" and not description:
                return self.send_json(400, {"error": "Write what the customer took"})
            conn = connect()
            customer = self.customer_or_404(conn, shop_id, customer_id)
            if not customer:
                conn.close()
                return
            entries = customer_entries(conn, shop_id, customer_id)
            before = balance_of(entries)
            if kind == "payment" and amount > before:
                conn.close()
                return self.send_json(400, {"error": "The payment is larger than the customer balance", "balance": before})
            cur = conn.execute(
                """INSERT INTO entries (shop_id, customer_id, kind, entry_date, description, amount, flagged)
                   VALUES (?, ?, ?, ?, ?, ?, 0)""",
                (shop_id, customer_id, kind, day, description, amount),
            )
            new_id = cur.lastrowid
            limit = float(customer["credit_limit"])
            flagged = False
            rows = statement_rows(customer_entries(conn, shop_id, customer_id))
            for row in rows:
                mark = row["kind"] == "debt" and limit > 0 and row["running_balance"] > limit
                if bool(row["flagged"]) != mark:
                    conn.execute("UPDATE entries SET flagged = ? WHERE id = ?", (int(mark), row["id"]))
                if row["id"] == new_id:
                    flagged = mark
            conn.commit()
            row = conn.execute("SELECT * FROM entries WHERE id = ?", (new_id,)).fetchone()
            after = balance_of(customer_entries(conn, shop_id, customer_id))
            conn.close()
            return self.send_json(201, {"entry": entry_dict(row), "balance": after, "flagged": flagged})

        return self.send_json(404, {"error": "Route not found"})

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)
        if path in ("/", "/index.html"):
            with open(FRONTEND, "rb") as handle:
                body = handle.read()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)
            return
        if not path.startswith("/api/"):
            return self.send_json(404, {"error": "Route not found"})
        session = self.need_session()
        if not session:
            return
        shop_id = session["shop_id"]
        conn = connect()
        try:
            if path == "/api/me":
                shop = conn.execute("SELECT * FROM shops WHERE id = ?", (shop_id,)).fetchone()
                return self.send_json(200, {"username": session["username"], "shop": dict(shop)})

            if path == "/api/customers":
                term = (query.get("q", [""])[0] or "").strip()
                if term:
                    like = f"%{term}%"
                    rows = conn.execute(
                        """SELECT * FROM customers WHERE shop_id = ?
                           AND (name LIKE ? OR phone LIKE ?) ORDER BY name""",
                        (shop_id, like, like),
                    ).fetchall()
                else:
                    rows = conn.execute(
                        "SELECT * FROM customers WHERE shop_id = ? ORDER BY name", (shop_id,)
                    ).fetchall()
                customers = [customer_payload(conn, shop_id, row) for row in rows]
                return self.send_json(200, {"customers": customers})

            if path == "/api/board":
                as_of = (query.get("as_of", [date.today().isoformat()])[0])
                if not valid_day(as_of):
                    return self.send_json(400, {"error": "Invalid display date"})
                rows = conn.execute("SELECT * FROM customers WHERE shop_id = ? ORDER BY name", (shop_id,)).fetchall()
                customers = []
                all_open = []
                total = 0.0
                for row in rows:
                    item = customer_payload(conn, shop_id, row)
                    customers.append(item)
                    total += max(0.0, item["balance"])
                    entries = customer_entries(conn, shop_id, item["id"])
                    aged = aging_buckets(entries, as_of)
                    for open_debt in aged["open_debts"]:
                        all_open.append({
                            "customer_id": item["id"],
                            "customer_name": item["name"],
                            **open_debt,
                        })
                total_aging = {"0-7": 0.0, "8-30": 0.0, "30+": 0.0}
                for item in all_open:
                    total_aging[item["bucket"]] = round(total_aging[item["bucket"]] + item["left"], 2)
                all_open.sort(key=lambda item: (-item["age_days"], item["day"]))
                debtors = sorted(
                    [item for item in customers if item["balance"] > 0],
                    key=lambda item: -item["balance"],
                )
                return self.send_json(200, {
                    "as_of": as_of,
                    "total_outstanding": round(total, 2),
                    "customers_with_balance": len(debtors),
                    "top_debtors": debtors[:5],
                    "over_limit": [item for item in customers if item["over_limit"]],
                    "aging": total_aging,
                    "oldest_unpaid": all_open[:10],
                })

            match = re.fullmatch(r"/api/customers/(\d+)", path)
            if match:
                row = self.customer_or_404(conn, shop_id, int(match.group(1)))
                if not row:
                    return
                payload = customer_payload(conn, shop_id, row)
                payload["entries"] = statement_rows(customer_entries(conn, shop_id, payload["id"]))
                return self.send_json(200, {"customer": payload})

            match = re.fullmatch(r"/api/customers/(\d+)/reminder", path)
            if match:
                row = self.customer_or_404(conn, shop_id, int(match.group(1)))
                if not row:
                    return
                payload = customer_payload(conn, shop_id, row)
                shop = conn.execute("SELECT name FROM shops WHERE id = ?", (shop_id,)).fetchone()
                balance = f"{payload['balance']:,.2f}".rstrip("0").rstrip(".")
                text = (
                    f"Good evening {payload['name']}, this is {shop['name']}. "
                    f"A friendly reminder that your account balance with us is {balance} EGP. "
                    "You are welcome to settle part or all of it whenever suits you. Thank you for dealing with us."
                )
                return self.send_json(200, {"text": text, "balance": payload["balance"]})

            if path == "/api/export/ledger.csv":
                rows = conn.execute(
                    """SELECT c.name AS customer_name, c.phone, e.entry_date, e.kind,
                              e.description, e.amount, e.flagged
                       FROM entries e JOIN customers c ON c.id = e.customer_id
                       WHERE e.shop_id = ? ORDER BY c.name, e.entry_date, e.id""",
                    (shop_id,),
                ).fetchall()
                output = io.StringIO(newline="")
                writer = csv.writer(output)
                writer.writerow(["customer_name", "phone", "entry_date", "kind", "description", "amount", "over_limit_flag"])
                for row in rows:
                    writer.writerow([row["customer_name"], row["phone"], row["entry_date"], row["kind"], row["description"], row["amount"], row["flagged"]])
                return self.send_text(200, output.getvalue(), "text/csv; charset=utf-8", "daftar-ledger.csv")

            return self.send_json(404, {"error": "Route not found"})
        finally:
            conn.close()

    def log_message(self, format, *args):
        pass


def main():
    port = int(os.environ.get("PORT", "8091"))
    print(f"Daftar is running at http://127.0.0.1:{port}")
    ThreadingHTTPServer(("127.0.0.1", port), DaftarHandler).serve_forever()


if __name__ == "__main__":
    main()
