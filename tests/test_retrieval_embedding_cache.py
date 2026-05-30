"""Tests for RetrievalEmbeddingCache."""

import asyncio
import time

from app.memory.retrieval_embedding_cache import (
    RetrievalEmbeddingCache,
    _normalize_query,
    get_retrieval_cache,
    init_retrieval_cache,
)


class TestNormalizeQuery:
    def test_trims_whitespace(self):
        assert _normalize_query("  hello  ") == "hello"

    def test_collapses_whitespace(self):
        assert _normalize_query("hello   world") == "hello world"

    def test_collapses_newlines_and_tabs(self):
        assert _normalize_query("hello\n\t  world") == "hello world"

    def test_empty_string(self):
        assert _normalize_query("   ") == ""


class TestRetrievalEmbeddingCache:
    def test_put_and_get(self):
        cache = RetrievalEmbeddingCache(ttl_seconds=60.0, capacity=10)
        vec = [0.1, 0.2, 0.3]
        cache.put("model-a", "hello world", vec)
        result = cache.get("model-a", "hello world")
        assert result == vec

    def test_miss_on_unknown_key(self):
        cache = RetrievalEmbeddingCache()
        assert cache.get("model-a", "never seen") is None

    def test_hit_on_exact_match_only(self):
        cache = RetrievalEmbeddingCache()
        cache.put("model-a", "hello world", [1.0, 2.0])
        # Different model -> miss
        assert cache.get("model-b", "hello world") is None
        # Different text -> miss
        assert cache.get("model-a", "hello world!") is None

    def test_normalized_whitespace_hits(self):
        cache = RetrievalEmbeddingCache()
        cache.put("model-a", "  hello   world  ", [1.0, 2.0])
        result = cache.get("model-a", "hello world")
        assert result == [1.0, 2.0]

    def test_returns_copy_not_reference(self):
        cache = RetrievalEmbeddingCache()
        vec = [1.0, 2.0, 3.0]
        cache.put("model-a", "test", vec)
        result = cache.get("model-a", "test")
        result[0] = 99.0
        # Original cached value unchanged
        assert cache.get("model-a", "test") == [1.0, 2.0, 3.0]

    def test_ttl_expiration(self):
        cache = RetrievalEmbeddingCache(ttl_seconds=0.01, capacity=10)
        cache.put("model-a", "test", [1.0])
        assert cache.get("model-a", "test") == [1.0]
        time.sleep(0.02)
        assert cache.get("model-a", "test") is None

    def test_capacity_eviction_lru(self):
        cache = RetrievalEmbeddingCache(ttl_seconds=60.0, capacity=2)
        cache.put("m", "a", [1.0])
        cache.put("m", "b", [2.0])
        cache.put("m", "c", [3.0])
        # "a" should be evicted (oldest, never accessed again)
        assert cache.get("m", "a") is None
        assert cache.get("m", "b") == [2.0]
        assert cache.get("m", "c") == [3.0]
        assert cache.stats.evictions == 1

    def test_access_moves_to_end(self):
        cache = RetrievalEmbeddingCache(ttl_seconds=60.0, capacity=2)
        cache.put("m", "a", [1.0])
        cache.put("m", "b", [2.0])
        # Access "a" -> moves to end, "b" becomes LRU
        cache.get("m", "a")
        cache.put("m", "c", [3.0])
        # "b" should be evicted
        assert cache.get("m", "a") == [1.0]
        assert cache.get("m", "b") is None
        assert cache.get("m", "c") == [3.0]

    def test_clear(self):
        cache = RetrievalEmbeddingCache()
        cache.put("m", "a", [1.0])
        cache.put("m", "b", [2.0])
        assert len(cache) == 2
        cache.clear()
        assert len(cache) == 0
        assert cache.get("m", "a") is None

    def test_stats_tracking(self):
        cache = RetrievalEmbeddingCache()
        cache.get("m", "miss1")  # miss
        cache.get("m", "miss2")  # miss
        cache.put("m", "hit", [1.0])
        cache.get("m", "hit")  # hit
        cache.get("m", "hit")  # hit
        assert cache.stats.misses == 2
        assert cache.stats.hits == 2
        assert cache.stats.hit_rate == 0.5

    def test_put_same_key_updates_value(self):
        cache = RetrievalEmbeddingCache()
        cache.put("m", "test", [1.0])
        cache.put("m", "test", [9.0])
        assert cache.get("m", "test") == [9.0]
        assert len(cache) == 1

    def test_zero_capacity_clamped(self):
        cache = RetrievalEmbeddingCache(capacity=0)
        assert cache.capacity == 1


class TestSingleton:
    def test_get_retrieval_cache_returns_same_instance(self):
        init_retrieval_cache(ttl_seconds=60.0, capacity=5)
        c1 = get_retrieval_cache()
        c2 = get_retrieval_cache()
        assert c1 is c2

    def test_init_retrieval_cache_replaces_instance(self):
        init_retrieval_cache(ttl_seconds=10.0, capacity=3)
        c1 = get_retrieval_cache()
        init_retrieval_cache(ttl_seconds=20.0, capacity=7)
        c2 = get_retrieval_cache()
        assert c1 is not c2
        assert c2.ttl_seconds == 20.0
        assert c2.capacity == 7


class TestIntegrationRetrieveCardsUsesCache:
    def test_retrieve_cards_uses_cache_for_embedding(self, tmp_path):
        """Verify retrieve_cards hits the retrieval cache on repeated queries."""
        async def run():
            from app.memory.card_retriever import retrieve_cards
            from app.memory.query_builder import build_retrieval_query
            from app.providers.embedding_dummy import DummyEmbeddingProvider
            from app.storage.sqlite_cards import (
                create_memory_library,
                init_cards_db,
                insert_card,
                set_conversation_mounts,
            )
            from app.storage.sqlite_vector_store import SqliteVectorStore
            from app.storage.vector_sync import sync_card_vector

            db_path = str(tmp_path / "memory.sqlite")
            await init_cards_db(db_path)

            lib_id = await create_memory_library(db_path, name="test", library_id="lib_test")
            await set_conversation_mounts(db_path, "conv1", [lib_id], write_library_id=lib_id, user_id="u1", character_id="c1")

            await insert_card(db_path, "card1", lib_id, "u1", "c1", "conv1", "global", "fact", "test content", 0.8, 0.9, "approved")
            embedding = DummyEmbeddingProvider(dimension=8)
            store = SqliteVectorStore(db_path=str(tmp_path / "vec.sqlite"), table_name="memory", dimension=8)
            store.connect()
            await sync_card_vector(db_path, "card1", embedding, store)

            init_retrieval_cache(ttl_seconds=60.0, capacity=16)
            cache = get_retrieval_cache()

            query = build_retrieval_query(
                [{"role": "user", "content": "test"}], "u1", "c1", "conv1",
            )

            stats_before = (cache.stats.hits, cache.stats.misses)
            await retrieve_cards(query, embedding, store, db_path, vector_top_k=10, final_top_k=5)
            assert cache.stats.misses > stats_before[1]

            stats_before = (cache.stats.hits, cache.stats.misses)
            await retrieve_cards(query, embedding, store, db_path, vector_top_k=10, final_top_k=5)
            assert cache.stats.hits > stats_before[0]

        asyncio.run(run())

    def test_write_path_sync_card_vector_does_not_use_cache(self, tmp_path):
        """sync_card_vector should NOT check the retrieval cache."""
        async def run():
            from app.providers.embedding_dummy import DummyEmbeddingProvider
            from app.storage.sqlite_cards import init_cards_db, insert_card
            from app.storage.sqlite_vector_store import SqliteVectorStore
            from app.storage.vector_sync import sync_card_vector

            db_path = str(tmp_path / "memory.sqlite")
            await init_cards_db(db_path)
            await insert_card(db_path, "card1", "lib", "u1", "c1", "conv1", "global", "fact", "content", 0.8, 0.9, "approved")

            init_retrieval_cache(ttl_seconds=60.0, capacity=16)
            cache = get_retrieval_cache()
            hits_before = cache.stats.hits

            embedding = DummyEmbeddingProvider(dimension=8)
            store = SqliteVectorStore(db_path=str(tmp_path / "vec.sqlite"), table_name="memory", dimension=8)
            store.connect()
            await sync_card_vector(db_path, "card1", embedding, store)

            assert cache.stats.hits == hits_before

        asyncio.run(run())
