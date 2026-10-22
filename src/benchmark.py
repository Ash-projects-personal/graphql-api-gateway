"""
Measured comparisons, all against the local stand ins:

1. N+1 check: query all 10 users with their orders, first with the
   per user resolver (1 list call + 10 calls) and then with the
   batching loader (1 list call + 1 batch call). Downstream call
   counts come from the services' own counters.
2. Every root field: one query per schema field, proving each resolves.
3. Cache: the same product query repeated 20 times; hits and misses
   counted by the cache itself.
4. Latency: the users with orders page query timed over 25 runs.
5. HTTP smoke test against the real server process.
"""

import asyncio
import json
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from aiohttp import web

import gateway
from downstream import COUNTER
from gateway import product_cache, run_query
from server import make_app

PAGE_QUERY = "{ users { id name orders { id status product { name } } } }"


async def main_async() -> dict:
    # The product cache is cleared before each run. The first version of
    # this benchmark did not clear it, so the loader run silently reused
    # products cached by the naive run and the comparison was rigged in
    # the loader's favour. Both runs now start from a cold cache.
    product_cache._store.clear()
    COUNTER.reset()
    await run_query(PAGE_QUERY, use_loader=False)
    naive_counts = dict(COUNTER.counts)

    product_cache._store.clear()
    COUNTER.reset()
    ctx_data = await run_query(PAGE_QUERY, use_loader=True)
    loader_counts = dict(COUNTER.counts)

    root_fields = {}
    checks = {
        "user": ('{ user(id: "u1") { name email } }', "user"),
        "users": ("{ users { id } }", "users"),
        "order": ('{ order(id: "o101") { status quantity } }', "order"),
        "orders": ("{ orders { id } }", "orders"),
        "product": ('{ product(id: "p1") { name priceCents } }', "product"),
        "products": ("{ products { id name } }", "products"),
        "inventory": ('{ inventory(productId: "p1") { stock } }', "inventory"),
        "notifications": ('{ notifications(userId: "u1") { message read } }', "notifications"),
    }
    for label, (query, key) in checks.items():
        data = await run_query(query)
        value = data[key]
        root_fields[label] = len(value) if isinstance(value, list) else (value is not None)

    product_cache.hits = 0
    product_cache.misses = 0
    product_cache._store.clear()
    for _ in range(20):
        await run_query('{ product(id: "p2") { name priceCents } }')
    cache_result = {"hits": product_cache.hits, "misses": product_cache.misses}

    async def time_mode(use_loader: bool) -> dict:
        product_cache._store.clear()
        values = []
        for _ in range(25):
            start = time.perf_counter()
            await run_query(PAGE_QUERY, use_loader=use_loader)
            values.append((time.perf_counter() - start) * 1000)
        return {
            "mean_ms": round(sum(values) / len(values), 2),
            "min_ms": round(min(values), 2),
            "max_ms": round(max(values), 2),
            "runs": len(values),
        }

    latency = {
        "with_loader": await time_mode(True),
        "without_loader": await time_mode(False),
    }

    runner = web.AppRunner(make_app())
    await runner.setup()
    await web.TCPSite(runner, "127.0.0.1", 8941).start()
    try:
        def post(query: str):
            req = urllib.request.Request(
                "http://127.0.0.1:8941/graphql",
                data=json.dumps({"query": query}).encode(),
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                return json.loads(resp.read().decode())
        http_result = await asyncio.to_thread(post, '{ product(id: "p3") { name inventory { stock } } }')
    finally:
        await runner.cleanup()

    metrics = {
        "repo": "graphql-api-gateway",
        "downstream": "five local in-process stand ins with call counters and a 5 ms simulated hop; not real microservices",
        "n_plus_one_check": {
            "query": "10 users, each with orders and product names",
            "calls_without_loader": naive_counts,
            "calls_total_without_loader": sum(naive_counts.values()),
            "calls_with_loader": loader_counts,
            "calls_total_with_loader": sum(loader_counts.values()),
        },
        "root_fields_resolved": root_fields,
        "product_cache": {
            "kind": "in-memory TTL cache in the gateway process (not Redis)",
            "ttl_seconds": gateway.CACHE_TTL_SECONDS,
            "repeated_product_queries": 20,
            **cache_result,
        },
        "page_query_latency": latency,
        "http_smoke_test": http_result.get("data"),
        "note": "Latency includes a 5 ms simulated downstream hop per service call, so read it as relative (loader versus no loader on identical conditions), not as a production response time. The old README claimed 320 ms down to 45 ms with no measurement anywhere; no such comparison exists for this code either, and none is claimed.",
    }
    ok = (
        metrics["n_plus_one_check"]["calls_total_with_loader"] < metrics["n_plus_one_check"]["calls_total_without_loader"]
        and all(v not in (False, 0) for v in root_fields.values())
        and cache_result["hits"] == 19
        and http_result.get("data", {}).get("product", {}).get("name") == "Wool Socks"
    )
    metrics["all_checks_passed"] = ok
    return metrics


def main() -> int:
    metrics = asyncio.run(main_async())
    out = ROOT / "outputs"
    out.mkdir(exist_ok=True)
    text = json.dumps(metrics, indent=2) + "\n"
    (out / "metrics.json").write_text(text)
    (out / "run_log.txt").write_text(text)
    print(text)
    return 0 if metrics["all_checks_passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
