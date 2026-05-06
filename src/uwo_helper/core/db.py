from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

from .models import Good, ObservationSource, Port, PriceObservation

SCHEMA_VERSION = 1

MIGRATIONS: list[str] = [
    """
    CREATE TABLE ports (
      id          INTEGER PRIMARY KEY,
      name        TEXT NOT NULL UNIQUE,
      region      TEXT,
      note        TEXT,
      created_at  TEXT NOT NULL DEFAULT (datetime('now'))
    );
    CREATE TABLE goods (
      id          INTEGER PRIMARY KEY,
      name        TEXT NOT NULL UNIQUE,
      category    TEXT,
      note        TEXT,
      created_at  TEXT NOT NULL DEFAULT (datetime('now'))
    );
    CREATE TABLE price_observations (
      id           INTEGER PRIMARY KEY,
      port_id      INTEGER NOT NULL REFERENCES ports(id),
      good_id      INTEGER NOT NULL REFERENCES goods(id),
      buy_price    INTEGER,
      sell_price   INTEGER,
      stock        INTEGER,
      observed_at  TEXT NOT NULL,
      source       TEXT NOT NULL CHECK (source IN ('manual','ocr','import')),
      screenshot   TEXT,
      note         TEXT,
      created_at   TEXT NOT NULL DEFAULT (datetime('now'))
    );
    CREATE INDEX idx_obs_good_observed ON price_observations(good_id, observed_at DESC);
    CREATE INDEX idx_obs_port_observed ON price_observations(port_id, observed_at DESC);
    """,
]


class Database:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        self._conn.execute("PRAGMA foreign_keys = ON;")
        self._conn.execute("PRAGMA journal_mode = WAL;")
        self._migrate()

    @classmethod
    def open(cls, path: Path) -> "Database":
        path.parent.mkdir(parents=True, exist_ok=True)
        return cls(sqlite3.connect(str(path), detect_types=sqlite3.PARSE_DECLTYPES))

    @classmethod
    def in_memory(cls) -> "Database":
        return cls(sqlite3.connect(":memory:"))

    def close(self) -> None:
        self._conn.close()

    # ----- migrations -----
    def _migrate(self) -> None:
        cur = self._conn.cursor()
        cur.execute(
            "CREATE TABLE IF NOT EXISTS schema_version (version INTEGER PRIMARY KEY);"
        )
        cur.execute("SELECT COALESCE(MAX(version), 0) FROM schema_version;")
        current = cur.fetchone()[0]
        for idx, sql in enumerate(MIGRATIONS, start=1):
            if idx <= current:
                continue
            cur.executescript(sql)
            cur.execute("INSERT INTO schema_version(version) VALUES (?);", (idx,))
        self._conn.commit()

    def list_tables(self) -> set[str]:
        rows = self._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table';"
        ).fetchall()
        return {r[0] for r in rows}

    # ----- ports -----
    def upsert_port(self, *, name: str, region: str | None = None) -> Port:
        cur = self._conn.cursor()
        cur.execute("SELECT id, name, region FROM ports WHERE name = ?;", (name,))
        row = cur.fetchone()
        if row is not None:
            return Port(id=row[0], name=row[1], region=row[2])
        cur.execute(
            "INSERT INTO ports(name, region) VALUES (?, ?);", (name, region)
        )
        self._conn.commit()
        return Port(id=cur.lastrowid, name=name, region=region)

    def list_ports(self) -> list[Port]:
        rows = self._conn.execute(
            "SELECT id, name, region FROM ports ORDER BY name;"
        ).fetchall()
        return [Port(id=r[0], name=r[1], region=r[2]) for r in rows]

    # ----- goods -----
    def upsert_good(self, *, name: str, category: str | None = None) -> Good:
        cur = self._conn.cursor()
        cur.execute("SELECT id, name, category FROM goods WHERE name = ?;", (name,))
        row = cur.fetchone()
        if row is not None:
            return Good(id=row[0], name=row[1], category=row[2])
        cur.execute(
            "INSERT INTO goods(name, category) VALUES (?, ?);", (name, category)
        )
        self._conn.commit()
        return Good(id=cur.lastrowid, name=name, category=category)

    def list_goods(self) -> list[Good]:
        rows = self._conn.execute(
            "SELECT id, name, category FROM goods ORDER BY name;"
        ).fetchall()
        return [Good(id=r[0], name=r[1], category=r[2]) for r in rows]

    # ----- observations -----
    def insert_observation(
        self,
        *,
        port_id: int,
        good_id: int,
        buy_price: int | None,
        sell_price: int | None,
        stock: int | None,
        observed_at: datetime,
        source: ObservationSource,
        screenshot: str | None,
        note: str | None,
    ) -> PriceObservation:
        cur = self._conn.cursor()
        cur.execute(
            """
            INSERT INTO price_observations
                (port_id, good_id, buy_price, sell_price, stock, observed_at, source, screenshot, note)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (port_id, good_id, buy_price, sell_price, stock, observed_at.isoformat(), source, screenshot, note),
        )
        self._conn.commit()
        new_id = cur.lastrowid
        return self._load_observation(new_id)

    def list_observations(
        self,
        *,
        limit: int | None = None,
        port_id: int | None = None,
        good_id: int | None = None,
    ) -> list[PriceObservation]:
        sql = (
            "SELECT o.id, o.port_id, o.good_id, o.buy_price, o.sell_price, o.stock, "
            "o.observed_at, o.source, o.screenshot, o.note, "
            "p.name, p.region, g.name, g.category "
            "FROM price_observations o "
            "JOIN ports p ON p.id = o.port_id "
            "JOIN goods g ON g.id = o.good_id "
        )
        params: list[object] = []
        clauses: list[str] = []
        if port_id is not None:
            clauses.append("o.port_id = ?")
            params.append(port_id)
        if good_id is not None:
            clauses.append("o.good_id = ?")
            params.append(good_id)
        if clauses:
            sql += "WHERE " + " AND ".join(clauses) + " "
        sql += "ORDER BY o.observed_at DESC"
        if limit is not None:
            sql += " LIMIT ?"
            params.append(limit)
        rows = self._conn.execute(sql, params).fetchall()
        return [_row_to_observation(r) for r in rows]

    def _load_observation(self, obs_id: int) -> PriceObservation:
        row = self._conn.execute(
            "SELECT o.id, o.port_id, o.good_id, o.buy_price, o.sell_price, o.stock, "
            "o.observed_at, o.source, o.screenshot, o.note, "
            "p.name, p.region, g.name, g.category "
            "FROM price_observations o "
            "JOIN ports p ON p.id = o.port_id "
            "JOIN goods g ON g.id = o.good_id "
            "WHERE o.id = ?;",
            (obs_id,),
        ).fetchone()
        if row is None:
            raise LookupError(f"observation {obs_id} not found")
        return _row_to_observation(row)


def _row_to_observation(row: tuple) -> PriceObservation:
    return PriceObservation(
        id=row[0],
        port=Port(id=row[1], name=row[10], region=row[11]),
        good=Good(id=row[2], name=row[12], category=row[13]),
        buy_price=row[3],
        sell_price=row[4],
        stock=row[5],
        observed_at=datetime.fromisoformat(row[6]),
        source=row[7],
        screenshot=row[8],
        note=row[9],
    )
