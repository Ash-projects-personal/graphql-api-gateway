import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from downstream import COUNTER
from gateway import product_cache, run_query


def run(coro):
    return asyncio.get_event_loop_policy().new_event_loop().run_until_complete(coro)


def test_every_root_field_resolves():
    async def go():
        assert (await run_query('{ user(id: "u1") { name } }'))["user"]["name"] == "Asha Rao"
        assert len((await run_query("{ users { id } }"))["users"]) == 10
        assert (await run_query('{ order(id: "o101") { status } }'))["order"]["status"] == "shipped"
        assert len((await run_query("{ orders { id } }"))["orders"]) == 20
        assert (await run_query('{ product(id: "p1") { name } }'))["product"]["name"] == "Trail Shoes"
        assert len((await run_query("{ products { id } }"))["products"]) == 4
        assert (await run_query('{ inventory(productId: "p1") { stock } }'))["inventory"]["stock"] == 40
        assert len((await run_query('{ notifications(userId: "u1") { id } }'))["notifications"]) == 2
    run(go())


def test_loader_reduces_downstream_calls():
    async def go():
        query = "{ users { id orders { id product { name } } } }"
        product_cache._store.clear()
        COUNTER.reset()
        await run_query(query, use_loader=False)
        naive = sum(COUNTER.counts.values())
        product_cache._store.clear()
        COUNTER.reset()
        await run_query(query, use_loader=True)
        batched = sum(COUNTER.counts.values())
        assert naive == 31
        assert batched == 3
    run(go())


def test_product_cache_counts_hits():
    async def go():
        product_cache._store.clear()
        product_cache.hits = 0
        product_cache.misses = 0
        for _ in range(5):
            await run_query('{ product(id: "p4") { name } }')
        assert product_cache.misses == 1
        assert product_cache.hits == 4
    run(go())
