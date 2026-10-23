from __future__ import annotations

from app.storage.vector_promote import promote_staging_table


class FakeTable:
    def __init__(self, name: str):
        self.name = name

    def to_arrow(self):
        return {"source": self.name, "rows": [1, 2, 3]}


class FakeDB:
    def __init__(self, *, rename_supported: bool):
        self.rename_supported = rename_supported
        self.dropped: list[str] = []
        self.renamed: list[tuple[str, str]] = []
        self.created: list[tuple[str, object]] = []

    def drop_table(self, name: str):
        self.dropped.append(name)

    def rename_table(self, source: str, target: str):
        if not self.rename_supported:
            raise RuntimeError("rename_table is not supported in LanceDB OSS")
        self.renamed.append((source, target))

    def open_table(self, name: str):
        return FakeTable(name)

    def create_table(self, name: str, data):
        self.created.append((name, data))


def test_promote_staging_prefers_rename():
    db = FakeDB(rename_supported=True)

    strategy = promote_staging_table(db, "memories", "memories_staging")

    assert strategy == "rename"
    assert db.renamed == [("memories_staging", "memories")]
    assert db.created == []


def test_promote_staging_copies_when_rename_is_unsupported():
    db = FakeDB(rename_supported=False)

    strategy = promote_staging_table(db, "memories", "memories_staging")

    assert strategy == "copy"
    assert db.created == [("memories", {"source": "memories_staging", "rows": [1, 2, 3]})]
    assert "memories_staging" in db.dropped
