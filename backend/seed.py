#!/usr/bin/env python3
import os
import secrets
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(__file__))
from app import DB_PATH, make_hash

SCHEMA = """
CREATE TABLE IF NOT EXISTS shops (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    shop_id INTEGER NOT NULL REFERENCES shops(id),
    username TEXT NOT NULL UNIQUE,
    salt TEXT NOT NULL,
    pw_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'owner'
);
CREATE TABLE IF NOT EXISTS customers (
    id INTEGER PRIMARY KEY,
    shop_id INTEGER NOT NULL REFERENCES shops(id),
    name TEXT NOT NULL,
    phone TEXT NOT NULL DEFAULT '',
    address TEXT NOT NULL DEFAULT '',
    note TEXT NOT NULL DEFAULT '',
    credit_limit REAL NOT NULL DEFAULT 0
);
CREATE UNIQUE INDEX IF NOT EXISTS customers_shop_phone
    ON customers(shop_id, phone) WHERE phone <> '';
CREATE TABLE IF NOT EXISTS entries (
    id INTEGER PRIMARY KEY,
    shop_id INTEGER NOT NULL REFERENCES shops(id),
    customer_id INTEGER NOT NULL REFERENCES customers(id),
    kind TEXT NOT NULL CHECK(kind IN ('debt', 'payment')),
    entry_date TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    amount REAL NOT NULL CHECK(amount > 0),
    flagged INTEGER NOT NULL DEFAULT 0
);
"""

CUSTOMERS = [
    ("Hassan the Grocer", "01012010001", "Market Street", "Pays at the start of every month", 3000),
    ("Umm Karim", "01012010002", "Palm Alley", "", 1500),
    ("Mahmoud the Driver", "01012010003", "Microbus Station", "Daily wage work", 2000),
    ("Mona Abdel Rahman", "01012010004", "Yasmine Building", "", 1000),
    ("Ibrahim the Barber", "01012010005", "Next to the school", "", 2500),
    ("Souad the Seamstress", "01012010006", "El Gomhoreya Street", "", 1800),
    ("Khaled Abu Saree", "01012010007", "Village entrance", "Low limit because he is new", 700),
    ("Fatma El Zahraa", "01012010008", "The family house", "", 1200),
    ("Youssef the Carpenter", "01012010009", "The carpentry workshop", "", 4000),
    ("Noura Samy", "01012010010", "El Salam Tower", "Settled her account in full", 1000),
    ("Adel the Fisherman", "01012010011", "Sea Road", "", 2200),
    ("Hala Fathy", "01012010012", "Schools Street", "", 1600),
]

ENTRIES = [
    (1, "debt", "2026-09-14", "Sugar, rice and oil", 850),
    (1, "payment", "2026-09-20", "Cash payment", 300),
    (1, "debt", "2026-10-03", "Detergents and milk", 420),
    (1, "payment", "2026-10-18", "Payment from salary", 500),
    (2, "debt", "2026-09-28", "Vegetables and fruit", 610),
    (2, "debt", "2026-10-11", "Eggs and cheese", 390),
    (2, "payment", "2026-10-15", "Partial payment", 250),
    (3, "debt", "2026-10-01", "Cigarettes and drinks", 940),
    (3, "payment", "2026-10-08", "Weekly payment", 400),
    (3, "debt", "2026-10-21", "Household supplies", 680),
    (4, "debt", "2026-09-05", "Home tools", 780),
    (4, "debt", "2026-10-02", "Detergents", 460),
    (5, "debt", "2026-10-05", "Supplies for his shop", 1250),
    (5, "payment", "2026-10-12", "Transfer", 500),
    (5, "debt", "2026-10-19", "Small stock order", 300),
    (6, "debt", "2026-08-24", "Fabric and thread", 900),
    (6, "payment", "2026-09-10", "Old payment", 150),
    (7, "debt", "2026-10-09", "His first account entry", 500),
    (7, "debt", "2026-10-16", "Second order before settling", 430),
    (8, "debt", "2026-09-22", "Spices and herbs", 720),
    (8, "payment", "2026-09-29", "Payment", 200),
    (8, "debt", "2026-10-14", "Sugar and tea", 350),
    (9, "debt", "2026-09-18", "Workshop materials", 2100),
    (9, "payment", "2026-09-25", "First instalment", 800),
    (9, "debt", "2026-10-06", "Nails and paint", 950),
    (9, "payment", "2026-10-20", "Second instalment", 600),
    (10, "debt", "2026-09-30", "Household supplies", 650),
    (10, "payment", "2026-10-07", "Paid in full", 650),
    (11, "debt", "2026-10-10", "Nets and fishing tools", 1350),
    (11, "payment", "2026-10-17", "Payment", 450),
    (12, "debt", "2026-10-13", "Books and school supplies", 580),
    (12, "debt", "2026-10-22", "Weekly supplies", 260),
]


def flagged_entries(conn, shop_id):
    rows = conn.execute(
        """SELECT c.id, c.credit_limit FROM customers c WHERE c.shop_id = ?""", (shop_id,)
    ).fetchall()
    for customer_id, limit in rows:
        balance = 0.0
        entries = conn.execute(
            """SELECT id, kind, amount FROM entries
               WHERE shop_id = ? AND customer_id = ? ORDER BY entry_date, id""",
            (shop_id, customer_id),
        ).fetchall()
        for entry_id, kind, amount in entries:
            balance += amount if kind == "debt" else -amount
            flag = 1 if kind == "debt" and limit > 0 and balance > limit else 0
            conn.execute("UPDATE entries SET flagged = ? WHERE id = ?", (flag, entry_id))


def main():
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA)
    conn.execute("INSERT INTO shops (id, name) VALUES (1, 'El Nour Grocery')")
    salt = secrets.token_bytes(16)
    conn.execute(
        "INSERT INTO users (shop_id, username, salt, pw_hash) VALUES (1, 'shopkeeper', ?, ?)",
        (salt.hex(), make_hash("notebook123", salt)),
    )
    for name, phone, address, note, limit in CUSTOMERS:
        conn.execute(
            """INSERT INTO customers (shop_id, name, phone, address, note, credit_limit)
               VALUES (1, ?, ?, ?, ?, ?)""",
            (name, phone, address, note, limit),
        )
    ids = {
        phone: customer_id
        for customer_id, phone in conn.execute("SELECT id, phone FROM customers WHERE shop_id = 1")
    }
    phone_by_index = [row[1] for row in CUSTOMERS]
    for index, kind, day, description, amount in ENTRIES:
        phone = phone_by_index[index - 1]
        conn.execute(
            """INSERT INTO entries (shop_id, customer_id, kind, entry_date, description, amount)
               VALUES (1, ?, ?, ?, ?, ?)""",
            (ids[phone], kind, day, description, amount),
        )
    flagged_entries(conn, 1)
    conn.commit()
    total = conn.execute(
        """SELECT ROUND(SUM(CASE WHEN kind = 'debt' THEN amount ELSE -amount END), 2)
           FROM entries WHERE shop_id = 1"""
    ).fetchone()[0]
    conn.close()
    print(f"Seeded daftar.db at {DB_PATH}")
    print(f"Customers: {len(CUSTOMERS)}  Entries: {len(ENTRIES)}  Shop balance: {total}")


if __name__ == "__main__":
    main()
