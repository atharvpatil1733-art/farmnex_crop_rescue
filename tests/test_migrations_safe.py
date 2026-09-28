"""Migration safety net. Needs no database.

Scans every `.sql` file under `migrations/` and fails if it contains a
forbidden statement, or creates/touches any object that isn't `cr_`-prefixed.

This test must always pass and must never be weakened (CLAUDE.md "Database
safety rules"). If a legitimate migration needs something this test
rejects, the migration is wrong, not the test.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"

# Statements that must never appear, anywhere, for any reason.
FORBIDDEN_PATTERNS = [
    r"\bDROP\b",
    r"\bTRUNCATE\b",
    r"\bGRANT\b",
    r"\bREVOKE\b",
    r"\bCREATE\s+EXTENSION\b",
    r"\bCREATE\s+ROLE\b",
    r"\bALTER\s+ROLE\b",
    r"\bDROP\s+ROLE\b",
    r"\bCREATE\s+USER\b",
    r"\bALTER\s+USER\b",
    r"\bCREATE\s+SCHEMA\b",
    r"\bALTER\s+SCHEMA\b",
    r"\bCREATE\s+POLICY\b",
    r"\bALTER\s+POLICY\b",
    r"\bALTER\s+DATABASE\b",
    r"\bDROP\s+DATABASE\b",
    r"\bALTER\s+SYSTEM\b",
    r"\bRESET\b",
    r"\bpg_terminate_backend\b",
]

# The only ALTER TABLE actions this repo may ever run, and only on cr_ tables.
ALLOWED_ALTER_ACTIONS = [
    re.compile(r"^ENABLE\s+ROW\s+LEVEL\s+SECURITY\b", re.IGNORECASE),
    re.compile(r"^ADD\s+COLUMN\s+IF\s+NOT\s+EXISTS\b", re.IGNORECASE),
]


def _sql_files() -> list[Path]:
    if not MIGRATIONS_DIR.is_dir():
        return []
    return sorted(MIGRATIONS_DIR.glob("*.sql"))


def _strip_comments(sql: str) -> str:
    """Remove `-- ...` line comments so they can't hide or fake a match."""
    return "\n".join(line.split("--", 1)[0] for line in sql.splitlines())


@pytest.fixture(params=_sql_files(), ids=lambda p: p.name)
def sql_file(request) -> Path:
    return request.param


def test_at_least_one_migration_exists():
    assert _sql_files(), f"no .sql files found under {MIGRATIONS_DIR}"


def test_no_forbidden_statement(sql_file: Path):
    code = _strip_comments(sql_file.read_text(encoding="utf-8"))
    for pattern in FORBIDDEN_PATTERNS:
        match = re.search(pattern, code, re.IGNORECASE)
        assert match is None, f"{sql_file.name}: forbidden statement matched {pattern!r}: {match.group(0)!r}"


def test_every_created_or_touched_object_is_cr_prefixed(sql_file: Path):
    code = _strip_comments(sql_file.read_text(encoding="utf-8"))

    creates = re.findall(
        r"\bCREATE\s+(?:OR\s+REPLACE\s+)?(?:TABLE|INDEX|VIEW)\s+(?:IF\s+NOT\s+EXISTS\s+)?([A-Za-z0-9_.\"]+)",
        code,
        re.IGNORECASE,
    )
    writes = re.findall(
        r"\b(?:INSERT\s+INTO|UPDATE|DELETE\s+FROM)\s+([A-Za-z0-9_.\"]+)",
        code,
        re.IGNORECASE,
    )
    for name in creates + writes:
        bare = name.strip('"').split(".")[-1]
        assert bare.lower().startswith("cr_"), f"{sql_file.name}: non-cr_ object touched: {name!r}"

    # CREATE INDEX ... ON <table>: the table must be cr_-prefixed too.
    index_targets = re.findall(
        r"\bCREATE\s+INDEX\s+(?:IF\s+NOT\s+EXISTS\s+)?[A-Za-z0-9_\"]+\s+ON\s+([A-Za-z0-9_.\"]+)",
        code,
        re.IGNORECASE,
    )
    for name in index_targets:
        bare = name.strip('"').split(".")[-1]
        assert bare.lower().startswith("cr_"), f"{sql_file.name}: index created on non-cr_ table: {name!r}"


def test_alter_table_only_enables_rls_or_adds_a_column_on_a_cr_table(sql_file: Path):
    code = _strip_comments(sql_file.read_text(encoding="utf-8"))

    for match in re.finditer(
        r"\bALTER\s+TABLE\s+([A-Za-z0-9_.\"]+)\s+(.*?);", code, re.IGNORECASE | re.DOTALL
    ):
        table, action = match.group(1), match.group(2).strip()
        bare = table.strip('"').split(".")[-1]
        assert bare.lower().startswith("cr_"), f"{sql_file.name}: ALTER TABLE on non-cr_ table: {table!r}"
        assert any(pattern.match(action) for pattern in ALLOWED_ALTER_ACTIONS), (
            f"{sql_file.name}: disallowed ALTER TABLE action on {table!r}: {action!r}"
        )


def test_migration_is_wrapped_in_a_transaction(sql_file: Path):
    code = _strip_comments(sql_file.read_text(encoding="utf-8")).upper()
    assert "BEGIN" in code, f"{sql_file.name}: must be wrapped in BEGIN ... COMMIT"
    assert "COMMIT" in code, f"{sql_file.name}: must be wrapped in BEGIN ... COMMIT"


def test_demo_seed_only_inserts_and_is_conflict_safe():
    seed = MIGRATIONS_DIR / "002_demo_seed.sql"
    if not seed.exists():
        pytest.skip("002_demo_seed.sql not present yet")
    code = _strip_comments(seed.read_text(encoding="utf-8"))
    assert re.search(r"\bUPDATE\b", code, re.IGNORECASE) is None
    assert re.search(r"\bDELETE\b", code, re.IGNORECASE) is None
    assert re.search(r"\bINSERT\s+INTO\s+cr_demo_buyers\b", code, re.IGNORECASE)
    assert re.search(r"\bON\s+CONFLICT\b.*\bDO\s+NOTHING\b", code, re.IGNORECASE | re.DOTALL)
