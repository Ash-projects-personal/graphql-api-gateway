"""
GraphQL gateway over the five local downstream stand ins.

What is real here:
- A schema with resolvers for every field, including products and
  inventory, which the original repo's schema declared but never
  resolved.
- A DataLoader style batching loader for orders by user and products
  by id. Downstream call counts are measured and reported, so the N+1
  claim is a number, not an adjective.
- A TTL cache in front of product lookups. It is an in-memory cache in
  this process and is named that way everywhere. It is not Redis; the
  original README presented a JavaScript Map as Redis, and this rebuild
  does not repeat that. The TTL is 60 seconds, the value the original
  design used.
"""

import asyncio
import time
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

from graphql import build_schema, graphql

from downstream import (
    COUNTER,
    InventoryService,
    NotificationService,
    OrderService,
    ProductService,
    UserService,
)

CACHE_TTL_SECONDS = 60

SDL = """
type User { id: ID!, name: String!, email: String!, orders: [Order!]! }
type Order { id: ID!, quantity: Int!, status: String!, user: User!, product: Product! }
type Product { id: ID!, name: String!, priceCents: Int!, inventory: Inventory }
type Inventory { productId: ID!, stock: Int! }
type Notification { id: ID!, message: String!, read: Boolean! }
type Query {
  user(id: ID!): User
  users: [User!]!
  order(id: ID!): Order
  orders: [Order!]!
  product(id: ID!): Product
  products: [Product!]!
  inventory(productId: ID!): Inventory
  notifications(userId: ID!): [Notification!]!
}
"""

users_svc = UserService()
orders_svc = OrderService()
products_svc = ProductService()
inventory_svc = InventoryService()
notifications_svc = NotificationService()


class BatchLoader:
    """Collects keys requested in the same tick, resolves in one call."""

    def __init__(self, batch_fn):
        self.batch_fn = batch_fn
        self._queue: dict = {}
        self._scheduled = False
        self.batch_sizes: list[int] = []

    async def load(self, key):
        loop = asyncio.get_running_loop()
        fut = loop.create_future()
        self._queue.setdefault(key, []).append(fut)
        if not self._scheduled:
            self._scheduled = True
            loop.call_soon(self._dispatch)
        return await fut

    def _dispatch(self):
        queue, self._queue = self._queue, {}
        self._scheduled = False
        asyncio.ensure_future(self._run(queue))

    async def _run(self, queue):
        keys = list(queue.keys())
        self.batch_sizes.append(len(keys))
        results = await self.batch_fn(keys)
        for key, result in zip(keys, results):
            for fut in queue[key]:
                if not fut.done():
                    fut.set_result(result)


class TTLCache:
    """In-memory TTL cache. Not Redis, and named accordingly."""

    def __init__(self, ttl: float = CACHE_TTL_SECONDS):
        self.ttl = ttl
        self._store: dict = {}
        self.hits = 0
        self.misses = 0

    def get(self, key):
        entry = self._store.get(key)
        if entry and entry[1] > time.monotonic():
            self.hits += 1
            return entry[0]
        self.misses += 1
        return None

    def set(self, key, value) -> None:
        self._store[key] = (value, time.monotonic() + self.ttl)


product_cache = TTLCache()


async def fetch_product_cached(product_id: str):
    cached = product_cache.get(product_id)
    if cached is not None:
        return cached
    product = await products_svc.get_product(product_id)
    if product is not None:
        product_cache.set(product_id, product)
    return product


async def _product_batch(keys):
    """Cache aware batch fetch: one downstream call for all misses."""
    results: dict = {}
    missing = []
    for key in keys:
        cached = product_cache.get(key)
        if cached is not None:
            results[key] = cached
        else:
            missing.append(key)
    if missing:
        fetched = await products_svc.products_by_ids(missing)
        for key, value in zip(missing, fetched):
            if value is not None:
                product_cache.set(key, value)
            results[key] = value
    return [results[key] for key in keys]


def make_context(use_loader: bool) -> dict:
    return {
        "use_loader": use_loader,
        "orders_loader": BatchLoader(orders_svc.orders_for_users),
        "products_loader": BatchLoader(_product_batch),
    }


def build_gateway_schema():
    schema = build_schema(SDL)
    q = schema.type_map["Query"].fields
    user_t = schema.type_map["User"].fields
    order_t = schema.type_map["Order"].fields
    product_t = schema.type_map["Product"].fields

    async def resolve_user(obj, info, id):
        return await users_svc.get_user(id)

    async def resolve_users(obj, info):
        return await users_svc.list_users()

    async def resolve_order(obj, info, id):
        return await orders_svc.get_order(id)

    async def resolve_orders(obj, info):
        return await orders_svc.list_orders()

    async def resolve_product(obj, info, id):
        return await fetch_product_cached(id)

    async def resolve_products(obj, info):
        return await products_svc.list_products()

    async def resolve_inventory(obj, info, productId):
        return await inventory_svc.get_inventory(productId)

    async def resolve_notifications(obj, info, userId):
        return await notifications_svc.notifications_for_user(userId)

    async def resolve_user_orders(user, info):
        if info.context["use_loader"]:
            return await info.context["orders_loader"].load(user["id"])
        return await orders_svc.orders_for_user(user["id"])

    async def resolve_order_user(order, info):
        return await users_svc.get_user(order["user_id"])

    async def resolve_order_product(order, info):
        if info.context["use_loader"]:
            return await info.context["products_loader"].load(order["product_id"])
        return await fetch_product_cached(order["product_id"])

    async def resolve_product_inventory(product, info):
        return await inventory_svc.get_inventory(product["id"])

    # Data dicts use snake_case keys; the schema is camelCase. These two
    # fields need explicit resolvers instead of the default key lookup.
    schema.type_map["Product"].fields["priceCents"].resolve = (
        lambda obj, info: obj["price_cents"]
    )
    schema.type_map["Inventory"].fields["productId"].resolve = (
        lambda obj, info: obj["product_id"]
    )

    q["user"].resolve = resolve_user
    q["users"].resolve = resolve_users
    q["order"].resolve = resolve_order
    q["orders"].resolve = resolve_orders
    q["product"].resolve = resolve_product
    q["products"].resolve = resolve_products
    q["inventory"].resolve = resolve_inventory
    q["notifications"].resolve = resolve_notifications
    user_t["orders"].resolve = resolve_user_orders
    order_t["user"].resolve = resolve_order_user
    order_t["product"].resolve = resolve_order_product
    product_t["inventory"].resolve = resolve_product_inventory
    return schema


SCHEMA = build_gateway_schema()


async def run_query(query: str, use_loader: bool = True, variables=None):
    result = await graphql(
        SCHEMA,
        query,
        variable_values=variables,
        context_value=make_context(use_loader),
    )
    if result.errors:
        raise RuntimeError(f"GraphQL errors: {result.errors}")
    return result.data
