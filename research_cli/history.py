"""Local history of reports in SQLite."""

import sqlite3
from datetime import datetime

from .config import DB_PATH


def open_db(path: str = DB_PATH) -> sqlite3.Connection:
    """Open (and create if needed) the history database."""
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row  # rows behave like dicts: row["question"]
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS reports (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT    NOT NULL,
            question   TEXT    NOT NULL,
            lang       TEXT    NOT NULL,
            deep       INTEGER NOT NULL DEFAULT 0,
            report     TEXT    NOT NULL
        );
        CREATE TABLE IF NOT EXISTS sources (
            report_id INTEGER NOT NULL REFERENCES reports(id) ON DELETE CASCADE,
            num       INTEGER NOT NULL,
            title     TEXT,
            url       TEXT    NOT NULL
        );
    """)
    return conn


def save_to_history(conn, question: str, lang: str, deep: bool,
                    report: str, sources: list[dict]) -> int:
    """Store a report and its sources. Returns the new report id."""
    with conn:  # commits on success, rolls back on error
        cur = conn.execute(
            "INSERT INTO reports (created_at, question, lang, deep, report) "
            "VALUES (?, ?, ?, ?, ?)",
            (datetime.now().isoformat(timespec="seconds"), question, lang, int(deep), report),
        )
        report_id = cur.lastrowid
        conn.executemany(
            "INSERT INTO sources (report_id, num, title, url) VALUES (?, ?, ?, ?)",
            [(report_id, i, s["title"], s["url"]) for i, s in enumerate(sources, 1)],
        )
    return report_id


def list_history(conn, limit: int = 20, term: str | None = None) -> list[sqlite3.Row]:
    """Most recent reports first, optionally filtered by a search term."""
    sql = "SELECT id, created_at, question, lang, deep FROM reports"
    params: list = []
    if term:
        sql += " WHERE question LIKE ? OR report LIKE ?"
        params += [f"%{term}%", f"%{term}%"]
    sql += " ORDER BY id DESC LIMIT ?"
    params.append(limit)
    return conn.execute(sql, params).fetchall()


def get_report(conn, report_id: int) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM reports WHERE id = ?", (report_id,)).fetchone()


def latest_report_id(conn) -> int | None:
    return conn.execute("SELECT MAX(id) AS id FROM reports").fetchone()["id"]


def print_history(rows: list[sqlite3.Row]) -> None:
    if not rows:
        print("No reports found.")
        return
    for r in rows:
        tags = r["lang"] + (", deep" if r["deep"] else "")
        print(f"#{r['id']:<4} {r['created_at'][:16].replace('T', ' ')}  [{tags}]  {r['question']}")
