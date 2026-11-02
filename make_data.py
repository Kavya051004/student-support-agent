"""Creates the sample (FAKE) dataset: data/students.json and data/staff.json.

You normally do NOT need to run this - the files are already in the repo.
Run it only if you want to regenerate / edit the dataset:    python make_data.py

All names, phone numbers, emails and fee amounts below are made up.
Demo passwords:  students -> Pass@<number>  (S1001 -> Pass@1001)    staff -> Staff@123
Passwords are stored as salted hashes (never as plain text).
"""
import json
from pathlib import Path

from agent.stores import hash_password

DATA = Path(__file__).parent / "data"

students = [
    {
        "student_id": "S1001", "name": "Aarav Mehta",
        "programme": "PGDM (Artificial Intelligence & Data Science)", "batch": "2025-27",
        "email": "aarav.mehta@example.edu", "phone": "9876500001",
        "fee": {"total_fee": 900000, "paid": 600000, "due_amount": 300000,
                "next_due_date": "2026-11-15", "status": "Pending"},
        "scholarship": {"name": "Merit Scholarship", "percent": 25, "status": "Active",
                        "amount_per_year": 225000, "next_review": "2027-06-30"},
    },
    {
        "student_id": "S1002", "name": "Diya Nair",
        "programme": "PGDM (Big Data Analytics)", "batch": "2025-27",
        "email": "diya.nair@example.edu", "phone": "9876500002",
        "fee": {"total_fee": 1100000, "paid": 1100000, "due_amount": 0,
                "next_due_date": None, "status": "Paid"},
        "scholarship": {"name": "Need-Based Aid", "percent": 40, "status": "Under Review",
                        "amount_per_year": 440000, "next_review": "2026-12-31"},
    },
    {
        "student_id": "S1003", "name": "Rohan Kulkarni",
        "programme": "PGDM (Artificial Intelligence & Data Science)", "batch": "2025-27",
        "email": "rohan.kulkarni@example.edu", "phone": "9876500003",
        "fee": {"total_fee": 850000, "paid": 400000, "due_amount": 450000,
                "next_due_date": "2026-10-15", "status": "Overdue"},
        "scholarship": {"name": "Corporate Sponsorship - Northwind Ltd", "percent": 50,
                        "status": "Active", "amount_per_year": 425000, "next_review": "2027-03-31"},
    },
    {
        "student_id": "S1004", "name": "Sneha Reddy",
        "programme": "PGDM (Big Data Analytics)", "batch": "2025-27",
        "email": "sneha.reddy@example.edu", "phone": "9876500004",
        "fee": {"total_fee": 950000, "paid": 650000, "due_amount": 300000,
                "next_due_date": "2026-11-15", "status": "Partially Paid"},
        "scholarship": {"name": "Merit Scholarship", "percent": 15, "status": "Active",
                        "amount_per_year": 142500, "next_review": "2027-06-30"},
    },
    {   # fee record deliberately missing -> used to test "tool error" handling
        "student_id": "S1005", "name": "Kabir Singh",
        "programme": "PGDM (Artificial Intelligence & Data Science)", "batch": "2025-27",
        "email": "kabir.singh@example.edu", "phone": "9876500005",
        "fee": None,
        "scholarship": None,
    },
]

for s in students:
    num = s["student_id"][1:]
    s["password_hash"] = hash_password(f"Pass@{num}", salt=f"salt{num}")

staff = [{
    "staff_id": "STAFF01", "name": "Meera Iyer (Student Services)", "role": "staff",
    "password_hash": hash_password("Staff@123", salt="saltstaff01"),
}]

(DATA / "students.json").write_text(json.dumps(students, indent=2), encoding="utf-8")
(DATA / "staff.json").write_text(json.dumps(staff, indent=2), encoding="utf-8")
print(f"Wrote {len(students)} students and {len(staff)} staff to {DATA}")
