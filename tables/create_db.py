import sqlite3
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
DB_PATH = BASE_DIR / "tables" / "heat_risk.db"

conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

with open(BASE_DIR / "tables" / "heat_risk.sql", "r") as f:
    cursor.executescript(f.read())

conn.commit()

conn.close()

