"""Generate OpenAPI JSON and entity schema from the FastAPI app and SQLAlchemy models.

No database or external service needed — runs purely in-memory.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://dummy:dummy@localhost/dummy")

from src.main import app  # noqa: E402
from src.models import *  # noqa: E402, F401, F403 — registers models on Base.metadata
from src.models.base import Base  # noqa: E402
from src.models.order import OrderLineModel, OrderModel  # noqa: E402, F401 — not in __init__.py

SERVICE_NAME = "order-service"
API_DIR = Path("docs/api")
SCHEMA_DIR = Path("docs/schema")
API_DIR.mkdir(parents=True, exist_ok=True)
SCHEMA_DIR.mkdir(parents=True, exist_ok=True)

# --- OpenAPI ---

spec = app.openapi()
(API_DIR / "openapi.json").write_text(json.dumps(spec, indent=2) + "\n")
print(f"Wrote docs/api/openapi.json ({len(spec.get('paths', {}))} paths)")

# --- Entity Schema (Markdown) ---


def col_type_str(col) -> str:
    return str(col.type)


def render_table(table, relationships: list) -> str:
    lines: list[str] = []
    lines.append(f"## Table: `{table.name}`")
    lines.append("")
    lines.append("| Column | Type | Nullable | PK | FK |")
    lines.append("|---|---|---|---|---|")

    for col in table.columns:
        nullable = "YES" if col.nullable else "NO"
        pk = "PK" if col.primary_key else ""
        fk = ""
        for fk_obj in col.foreign_keys:
            target = f"`{fk_obj.column.table.name}.{fk_obj.column.name}`"
            if fk_obj.ondelete:
                fk = f"{target} ON DELETE {fk_obj.ondelete}"
            else:
                fk = target
            break
        lines.append(f"| `{col.name}` | `{col_type_str(col)}` | {nullable} | {pk} | {fk} |")

    # Constraints
    uniques = []
    checks = []
    for constraint in table.constraints:
        ctype = type(constraint).__name__
        if ctype == "UniqueConstraint":
            cols = [c.name for c in constraint.columns]
            pk_cols = [c.name for c in table.primary_key.columns]
            if cols != pk_cols:
                col_list = ", ".join(f"`{c}`" for c in cols)
                name = f" ({constraint.name})" if constraint.name else ""
                uniques.append(f"- UNIQUE ({col_list}){name}")
        elif ctype == "CheckConstraint":
            name = f" ({constraint.name})" if constraint.name else ""
            checks.append(f"- CHECK `{constraint.sqltext}`{name}")

    if uniques or checks:
        lines.append("")
        lines.append("**Constraints:**")
        lines.extend(uniques)
        lines.extend(checks)

    # Indexes
    if table.indexes:
        lines.append("")
        lines.append("**Indexes:**")
        for idx in table.indexes:
            cols = ", ".join(f"`{c.name}`" for c in idx.columns)
            unique_label = "UNIQUE " if idx.unique else ""
            lines.append(f"- `{idx.name}`: {unique_label}({cols})")

    # Relationships
    if relationships:
        lines.append("")
        lines.append("**Relationships:**")
        for rel in relationships:
            direction = rel["direction"].replace("ONETOMANY", "one-to-many").replace("MANYTOONE", "many-to-one").replace("MANYTOMANY", "many-to-many")
            lines.append(f"- `{rel['name']}` → `{rel['target_table']}` ({direction})")

    return "\n".join(lines)


def extract_relationships() -> dict[str, list]:
    rels_by_table: dict[str, list] = {}
    for mapper in Base.registry.mappers:
        table_name = mapper.local_table.name
        rels = []
        for rel in mapper.relationships:
            rels.append({
                "name": rel.key,
                "target_table": rel.mapper.local_table.name,
                "direction": rel.direction.name,
            })
        if rels:
            rels_by_table[table_name] = rels
    return rels_by_table


rels_by_table = extract_relationships()
now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

md_lines: list[str] = [
    f"# Entity Schema: {SERVICE_NAME}",
    "",
    f"> Auto-generated from SQLAlchemy models on {now}. Do not edit manually.",
    "",
    "---",
    "",
]

for table in Base.metadata.sorted_tables:
    rels = rels_by_table.get(table.name, [])
    md_lines.append(render_table(table, rels))
    md_lines.append("")
    md_lines.append("---")
    md_lines.append("")

(SCHEMA_DIR / "entities.md").write_text("\n".join(md_lines))
print(f"Wrote docs/schema/entities.md ({len(Base.metadata.sorted_tables)} tables)")
