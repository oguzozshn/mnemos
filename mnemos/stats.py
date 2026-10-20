"""Overview statistics over the message store. Reads aggregates only, never message text."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

# Rough rule of thumb for mixed Turkish/English text; good enough for a cost ballpark.
CHARS_PER_TOKEN = 3.5


def est_tokens(chars: int | None) -> int:
    return round((chars or 0) / CHARS_PER_TOKEN)


@dataclass
class SourceStats:
    source: str
    conversations: int
    user_messages: int
    assistant_messages: int
    user_chars: int
    assistant_chars: int
    first: str | None
    last: str | None

    @property
    def user_tokens_est(self) -> int:
        return est_tokens(self.user_chars)

    @property
    def assistant_tokens_est(self) -> int:
        return est_tokens(self.assistant_chars)


@dataclass
class NoiseStats:
    classified: int
    unclassified: int
    noise_messages: int
    clean_chars: int
    pasted_chars: int
    by_reason: list[tuple[str, int]]  # reason -> number of my messages containing it
    by_lang: list[tuple[str, int]]

    @property
    def clean_tokens_est(self) -> int:
        return est_tokens(self.clean_chars)


def by_source(conn: sqlite3.Connection) -> list[SourceStats]:
    rows = conn.execute(
        """
        SELECT
            m.source,
            COUNT(DISTINCT m.conversation_id)                           AS conversations,
            SUM(m.role = 'user')                                        AS user_messages,
            SUM(m.role = 'assistant')                                   AS assistant_messages,
            COALESCE(SUM(CASE WHEN m.role = 'user' THEN LENGTH(m.text) END), 0)      AS user_chars,
            COALESCE(SUM(CASE WHEN m.role = 'assistant' THEN LENGTH(m.text) END), 0) AS assistant_chars,
            MIN(m.created_at)                                           AS first,
            MAX(m.created_at)                                           AS last
        FROM messages m
        GROUP BY m.source
        ORDER BY m.source
        """
    ).fetchall()
    return [SourceStats(**dict(r)) for r in rows]


def noise(conn: sqlite3.Connection) -> NoiseStats:
    """Noise filter results for my own messages."""
    row = conn.execute(
        """
        SELECT
            SUM(clean_version IS NOT NULL)                         AS classified,
            SUM(clean_version IS NULL)                             AS unclassified,
            SUM(is_noise = 1)                                      AS noise_messages,
            COALESCE(SUM(CASE WHEN is_noise = 0 THEN LENGTH(clean_text) END), 0) AS clean_chars,
            COALESCE(SUM(pasted_chars), 0)                         AS pasted_chars
        FROM messages WHERE role = 'user'
        """
    ).fetchone()
    reasons = conn.execute(
        """
        SELECT noise_reason, COUNT(*) FROM messages
        WHERE role = 'user' AND noise_reason IS NOT NULL
        GROUP BY noise_reason ORDER BY COUNT(*) DESC
        """
    ).fetchall()
    langs = conn.execute(
        """
        SELECT COALESCE(lang, 'unknown'), COUNT(*) FROM messages
        WHERE role = 'user' AND is_noise = 0
        GROUP BY 1 ORDER BY COUNT(*) DESC
        """
    ).fetchall()
    return NoiseStats(
        classified=row["classified"] or 0,
        unclassified=row["unclassified"] or 0,
        noise_messages=row["noise_messages"] or 0,
        clean_chars=row["clean_chars"],
        pasted_chars=row["pasted_chars"],
        by_reason=[(r[0], r[1]) for r in reasons],
        by_lang=[(r[0], r[1]) for r in langs],
    )


def user_messages_per_month(conn: sqlite3.Connection) -> list[tuple[str, str, int]]:
    """Rows of (month 'YYYY-MM', source, user message count)."""
    return [
        (r["month"], r["source"], r["n"])
        for r in conn.execute(
            """
            SELECT SUBSTR(created_at, 1, 7) AS month, source, COUNT(*) AS n
            FROM messages
            WHERE role = 'user'
            GROUP BY month, source
            ORDER BY month, source
            """
        )
    ]


def user_message_length_buckets(conn: sqlite3.Connection) -> list[tuple[str, int]]:
    """How long my messages are; very long ones are usually pasted code/logs."""
    return [
        (r["bucket"], r["n"])
        for r in conn.execute(
            """
            SELECT
                CASE
                    WHEN LENGTH(text) < 100   THEN '1. <100 chars'
                    WHEN LENGTH(text) < 500   THEN '2. 100-499'
                    WHEN LENGTH(text) < 2000  THEN '3. 500-1999'
                    WHEN LENGTH(text) < 10000 THEN '4. 2000-9999'
                    ELSE                           '5. 10000+ (likely pasted content)'
                END AS bucket,
                COUNT(*) AS n
            FROM messages
            WHERE role = 'user'
            GROUP BY bucket
            ORDER BY bucket
            """
        )
    ]
