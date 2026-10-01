"""Generates SYNTHETIC transactions (no real person's data). Seeded => reproducible.
Run from repo root: python data/generate_sample_data.py"""
import csv, random
from datetime import date
random.seed(42)
rows = []
def add(d, desc, amt, typ): rows.append((d.isoformat(), desc, amt, typ))

for m in (6, 7, 8, 9):
    add(date(2026, m, 1), "SALARY ACME TECH PVT LTD", 60000, "CREDIT")
    add(date(2026, m, 2), "RENT TRANSFER", 15000, "DEBIT")
    add(date(2026, m, 5), "NETFLIX.COM", 649, "DEBIT")
    add(date(2026, m, 7), "SPOTIFY INDIA", 119, "DEBIT")
    add(date(2026, m, 10), "AMAZON PRIME MEMBERSHIP", 299, "DEBIT")
    add(date(2026, m, 12), "ELECTRICITY BILL MSEDCL", random.randint(1400, 2200), "DEBIT")
    add(date(2026, m, 14), "AIRTEL POSTPAID", 599, "DEBIT")
    for _ in range(random.randint(6, 8)):
        add(date(2026, m, random.randint(3, 28)),
            random.choice(["SWIGGY*ORDER #%d" % random.randint(1000, 9999),
                           "ZOMATO ORDER %d" % random.randint(1000, 9999)]),
            random.randint(250, 550), "DEBIT")
    for _ in range(random.randint(5, 7)):
        add(date(2026, m, random.randint(3, 28)),
            random.choice(["UBER TRIP", "OLA CABS"]), random.randint(120, 380), "DEBIT")
    add(date(2026, m, random.randint(15, 25)), "AMAZON PAY %d" % random.randint(100, 999),
        random.randint(900, 3200), "DEBIT")
    add(date(2026, m, random.randint(15, 25)), "APOLLO PHARMACY", random.randint(300, 900), "DEBIT")
# Planted anomaly: unusually large food spend in September
add(date(2026, 9, 20), "ZOMATO ORDER 7788 PARTY", 6800, "DEBIT")
add(date(2026, 9, 21), "SWIGGY*ORDER #5521 CATERING", 3900, "DEBIT")
# Unknown merchants to exercise the ML / Needs Review path
add(date(2026, 8, 18), "XYZ STORE MUMBAI", 1250, "DEBIT")
add(date(2026, 9, 9), "UDEMY COURSE PURCHASE", 1499, "DEBIT")

rows.sort()
with open("data/sample_transactions.csv", "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["date", "description", "amount", "transaction_type"])
    w.writerows(rows)
print(len(rows), "synthetic rows written")
