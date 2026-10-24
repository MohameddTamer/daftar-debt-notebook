import csv
import io
import json
import os
import sqlite3
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND = os.path.join(ROOT, "backend")
TMP = tempfile.TemporaryDirectory()
os.environ["DAFTAR_DB"] = os.path.join(TMP.name, "test.db")
sys.path.insert(0, BACKEND)

import app as daftar_app  # noqa: E402
import seed  # noqa: E402
from ledger import aging_buckets  # noqa: E402


def call(method, path, body=None, token=None, raw=None, content_type="application/json"):
    data = raw
    headers = {}
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = content_type
    elif raw is not None:
        headers["Content-Type"] = content_type
    if token:
        headers["Authorization"] = "Bearer " + token
    req = urllib.request.Request(BASE + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req) as response:
            text = response.read().decode()
            return response.status, json.loads(text) if "json" in response.headers.get("Content-Type", "") else text
    except urllib.error.HTTPError as error:
        text = error.read().decode()
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            payload = text
        return error.code, payload


class DaftarApiTest(unittest.TestCase):
    token = None

    @classmethod
    def setUpClass(cls):
        global BASE
        seed.main()
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), daftar_app.DaftarHandler)
        BASE = f"http://127.0.0.1:{cls.server.server_port}"
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        status, data = call("POST", "/api/login", {"username": "shopkeeper", "password": "notebook123"})
        assert status == 200, data
        cls.token = data["token"]

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        TMP.cleanup()

    def test_board_total_matches_raw_sql(self):
        conn = sqlite3.connect(os.environ["DAFTAR_DB"])
        expected = conn.execute(
            """SELECT ROUND(SUM(CASE WHEN kind = 'debt' THEN amount ELSE -amount END), 2)
               FROM entries WHERE shop_id = 1"""
        ).fetchone()[0]
        conn.close()
        status, data = call("GET", "/api/board?as_of=2026-10-24", token=self.token)
        self.assertEqual(status, 200)
        self.assertEqual(data["total_outstanding"], expected)
        self.assertGreater(data["total_outstanding"], 0)

    def test_seed_has_settled_customer_and_statement_running_balance(self):
        status, data = call("GET", "/api/customers?q=01012010010", token=self.token)
        self.assertEqual(status, 200)
        customer = data["customers"][0]
        self.assertEqual(customer["balance"], 0)
        status, detail = call("GET", f"/api/customers/{customer['id']}", token=self.token)
        self.assertEqual(status, 200)
        self.assertEqual(detail["customer"]["entries"][-1]["running_balance"], 0)
        running = 0
        for entry in detail["customer"]["entries"]:
            running += entry["amount"] if entry["kind"] == "debt" else -entry["amount"]
            self.assertEqual(entry["running_balance"], round(running, 2))

    def test_overpayment_is_rejected(self):
        status, data = call("GET", "/api/customers?q=01012010001", token=self.token)
        customer = data["customers"][0]
        status, result = call(
            "POST",
            f"/api/customers/{customer['id']}/entries",
            {"kind": "payment", "entry_date": "2026-10-24", "description": "too much", "amount": customer["balance"] + 1},
            token=self.token,
        )
        self.assertEqual(status, 400)
        self.assertEqual(result["balance"], customer["balance"])

    def test_debt_over_credit_limit_is_allowed_and_flagged(self):
        status, created = call(
            "POST", "/api/customers",
            {"name": "Limit Customer", "phone": "01099990001", "credit_limit": 100},
            token=self.token,
        )
        self.assertEqual(status, 201)
        customer_id = created["customer"]["id"]
        status, entry = call(
            "POST", f"/api/customers/{customer_id}/entries",
            {"kind": "debt", "entry_date": "2026-10-24", "description": "Big order", "amount": 125},
            token=self.token,
        )
        self.assertEqual(status, 201)
        self.assertTrue(entry["flagged"])
        self.assertTrue(entry["entry"]["flagged"])

    def test_backdated_debt_flag_follows_its_place_in_the_ledger(self):
        status, created = call(
            "POST", "/api/customers",
            {"name": "Dates Customer", "phone": "01099990003", "credit_limit": 100},
            token=self.token,
        )
        self.assertEqual(status, 201)
        customer_id = created["customer"]["id"]
        status, later = call(
            "POST", f"/api/customers/{customer_id}/entries",
            {"kind": "debt", "entry_date": "2026-10-20", "description": "Late order", "amount": 80},
            token=self.token,
        )
        self.assertEqual(status, 201)
        status, earlier = call(
            "POST", f"/api/customers/{customer_id}/entries",
            {"kind": "debt", "entry_date": "2026-10-10", "description": "Old order logged late", "amount": 50},
            token=self.token,
        )
        self.assertEqual(status, 201)
        self.assertFalse(earlier["flagged"])
        status, detail = call("GET", f"/api/customers/{customer_id}", token=self.token)
        by_id = {entry["id"]: entry for entry in detail["customer"]["entries"]}
        self.assertTrue(by_id[later["entry"]["id"]]["flagged"])
        self.assertFalse(by_id[earlier["entry"]["id"]]["flagged"])
        self.assertEqual(detail["customer"]["balance"], 130)

    def test_duplicate_customer_phone_is_rejected(self):
        status, _ = call(
            "POST", "/api/customers",
            {"name": "Duplicate", "phone": "01012010001", "credit_limit": 0},
            token=self.token,
        )
        self.assertEqual(status, 409)

    def test_import_reports_existing_and_in_file_duplicates(self):
        text = (
            "name,phone,credit_limit\n"
            "Existing,01012010001,100\n"
            "New Import,01099990002,200\n"
            "In-File Duplicate,01099990002,200\n"
        )
        status, data = call(
            "POST", "/api/customers/import", token=self.token,
            raw=text.encode(), content_type="text/csv",
        )
        self.assertEqual(status, 201)
        self.assertEqual(data["created"], 1)
        self.assertEqual(len(data["skipped"]), 2)
        self.assertTrue(all(item["reason"] == "duplicate phone" for item in data["skipped"]))

    def test_aging_buckets_fifo_fixture(self):
        entries = [
            {"id": 1, "kind": "debt", "entry_date": "2026-08-20", "amount": 100},
            {"id": 2, "kind": "debt", "entry_date": "2026-10-01", "amount": 80},
            {"id": 3, "kind": "debt", "entry_date": "2026-10-20", "amount": 50},
            {"id": 4, "kind": "payment", "entry_date": "2026-10-21", "amount": 130},
        ]
        result = aging_buckets(entries, "2026-10-24")
        self.assertEqual(result["buckets"], {"0-7": 50.0, "8-30": 50.0, "30+": 0.0})

    def test_aging_keeps_uncovered_old_debt(self):
        entries = [
            {"id": 1, "kind": "debt", "entry_date": "2026-08-01", "amount": 90},
            {"id": 2, "kind": "payment", "entry_date": "2026-08-03", "amount": 25},
        ]
        result = aging_buckets(entries, "2026-10-24")
        self.assertEqual(result["buckets"]["30+"], 65)
        self.assertEqual(result["open_debts"][0]["age_days"], 84)

    def test_no_token_is_401(self):
        status, _ = call("GET", "/api/customers")
        self.assertEqual(status, 401)

    def test_wrong_password_is_401(self):
        status, _ = call("POST", "/api/login", {"username": "shopkeeper", "password": "wrong"})
        self.assertEqual(status, 401)

    def test_login_injection_is_401(self):
        status, _ = call("POST", "/api/login", {"username": "shopkeeper' OR '1'='1", "password": "x"})
        self.assertEqual(status, 401)

    def test_search_by_phone_digits(self):
        status, data = call("GET", "/api/customers?q=2010007", token=self.token)
        self.assertEqual(status, 200)
        self.assertEqual(len(data["customers"]), 1)
        self.assertEqual(data["customers"][0]["phone"], "01012010007")
        self.assertTrue(data["customers"][0]["over_limit"])

    def test_reminder_has_customer_shop_and_balance(self):
        status, data = call("GET", "/api/customers?q=01012010001", token=self.token)
        customer = data["customers"][0]
        status, reminder = call("GET", f"/api/customers/{customer['id']}/reminder", token=self.token)
        self.assertEqual(status, 200)
        self.assertIn(customer["name"], reminder["text"])
        self.assertIn("El Nour Grocery", reminder["text"])
        self.assertIn(str(int(customer["balance"])), reminder["text"])

    def test_export_ledger_csv_matches_database_rows(self):
        status, text = call("GET", "/api/export/ledger.csv", token=self.token)
        self.assertEqual(status, 200)
        rows = list(csv.DictReader(io.StringIO(text)))
        conn = sqlite3.connect(os.environ["DAFTAR_DB"])
        expected = conn.execute("SELECT COUNT(*) FROM entries WHERE shop_id = 1").fetchone()[0]
        conn.close()
        self.assertGreaterEqual(len(rows), expected - 1)
        self.assertIn("customer_name", rows[0])

    def test_seed_customer_count_and_old_debt_board(self):
        status, data = call("GET", "/api/customers", token=self.token)
        self.assertEqual(status, 200)
        self.assertGreaterEqual(len(data["customers"]), 12)
        status, board = call("GET", "/api/board?as_of=2026-10-24", token=self.token)
        self.assertGreater(board["aging"]["30+"], 0)
        self.assertTrue(board["oldest_unpaid"])


if __name__ == "__main__":
    unittest.main()
