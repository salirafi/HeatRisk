import sqlite3
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]

conn = sqlite3.connect(BASE_DIR / "tables" / "heat_risk.db")

with open(BASE_DIR / "tables" / "heat_risk.sql", "w") as f:
    for line in conn.iterdump():
        f.write(f"{line}\n")

conn.close()