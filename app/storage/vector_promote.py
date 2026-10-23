"""Promote a staging vector table into the live table, with a copy fallback."""

from __future__ import annotations

import contextlib
import logging

logger = logging.getLogger("kokoromemo.vector_promote")


def promote_staging_table(db, table_name: str, staging_name: str) -> str:
    """Replace the live table with staging, falling back when rename is unsupported.

    LanceDB OSS builds may not support ``rename_table``. In that case the staging
    table's Arrow data is copied into a freshly created live table.
    """
    with contextlib.suppress(Exception):
        db.drop_table(table_name)
    try:
        db.rename_table(staging_name, table_name)
        return "rename"
    except Exception as exc:
        logger.warning("rename_table unavailable (%s); recreating %s from staging", exc, table_name)

    staging = db.open_table(staging_name)
    data = staging.to_arrow()
    with contextlib.suppress(Exception):
        db.drop_table(table_name)
    db.create_table(table_name, data=data)
    with contextlib.suppress(Exception):
        db.drop_table(staging_name)
    return "copy"
