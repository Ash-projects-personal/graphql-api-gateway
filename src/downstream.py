"""
Local stand ins for the five downstream services.

Each service owns a small in-memory dataset and counts every call it
receives. The counts are the point: they let the gateway demo prove,
with numbers, how many downstream calls a query costs with and without
batching and caching. These are local stand ins, not real microservices,
and the README says so. Each call sleeps 5 ms to stand in for a network
hop, which keeps the latency measurements honest about being relative
to a simulated hop rather than a real service.
"""

import asyncio

USERS = [
    {"id": "u1", "name": "Asha Rao", "email": "asha@example.com"},
    {"id": "u2", "name": "Ben Ortiz", "email": "ben@example.com"},
    {"id": "u3", "name": "Cara Lin", "email": "cara@example.com"},
    {"id": "u4", "name": "Dev Patel", "email": "dev@example.com"},
    {"id": "u5", "name": "Erin Moss", "email": "erin@example.com"},
    {"id": "u6", "name": "Finn Cole", "email": "finn@example.com"},
    {"id": "u7", "name": "Gia Park", "email": "gia@example.com"},
    {"id": "u8", "name": "Hugo Reyes", "email": "hugo@example.com"},
    {"id": "u9", "name": "Ivy Chen", "email": "ivy@example.com"},
    {"id": "u10", "name": "Jay Novak", "email": "jay@example.com"},
]

PRODUCTS = [
    {"id": "p1", "name": "Trail Shoes", "price_cents": 12999},
    {"id": "p2", "name": "Rain Jacket", "price_cents": 18999},
    {"id": "p3", "name": "Wool Socks", "price_cents": 1999},
    {"id": "p4", "name": "Day Pack", "price_cents": 8999},
]

ORDERS = []
_oid = 100
for i, user in enumerate(USERS):
    for j in range(2):
        _oid += 1
        ORDERS.append(
            {
                "id": f"o{_oid}",
                "user_id": user["id"],
                "product_id": PRODUCTS[(i + j) % len(PRODUCTS)]["id"],
                "quantity": j + 1,
                "status": "shipped" if j == 0 else "processing",
            }
        )

INVENTORY = {p["id"]: {"product_id": p["id"], "stock": 40 - 7 * i} for i, p in enumerate(PRODUCTS)}

NOTIFICATIONS = [
    {"id": "n1", "user_id": "u1", "message": "Your order o101 shipped", "read": True},
    {"id": "n2", "user_id": "u1", "message": "Your order o102 is processing", "read": False},
    {"id": "n3", "user_id": "u2", "message": "Your order o103 shipped", "read": False},
]

HOP_SECONDS = 0.005


class CallCounter:
    def __init__(self) -> None:
        self.counts: dict[str, int] = {}

    def hit(self, name: str) -> None:
        self.counts[name] = self.counts.get(name, 0) + 1

    def reset(self) -> None:
        self.counts = {}


COUNTER = CallCounter()


class UserService:
    async def get_user(self, user_id: str):
        COUNTER.hit("users.get_user")
        await asyncio.sleep(HOP_SECONDS)
        return next((u for u in USERS if u["id"] == user_id), None)

    async def list_users(self):
        COUNTER.hit("users.list_users")
        await asyncio.sleep(HOP_SECONDS)
        return list(USERS)


class OrderService:
    async def get_order(self, order_id: str):
        COUNTER.hit("orders.get_order")
        await asyncio.sleep(HOP_SECONDS)
        return next((o for o in ORDERS if o["id"] == order_id), None)

    async def list_orders(self):
        COUNTER.hit("orders.list_orders")
        await asyncio.sleep(HOP_SECONDS)
        return list(ORDERS)

    async def orders_for_user(self, user_id: str):
        COUNTER.hit("orders.orders_for_user")
        await asyncio.sleep(HOP_SECONDS)
        return [o for o in ORDERS if o["user_id"] == user_id]

    async def orders_for_users(self, user_ids: list[str]):
        """One batched call for many users. This is what the loader uses."""
        COUNTER.hit("orders.orders_for_users_BATCH")
        await asyncio.sleep(HOP_SECONDS)
        return [[o for o in ORDERS if o["user_id"] == uid] for uid in user_ids]


class ProductService:
    async def get_product(self, product_id: str):
        COUNTER.hit("products.get_product")
        await asyncio.sleep(HOP_SECONDS)
        return next((p for p in PRODUCTS if p["id"] == product_id), None)

    async def list_products(self):
        COUNTER.hit("products.list_products")
        await asyncio.sleep(HOP_SECONDS)
        return list(PRODUCTS)

    async def products_by_ids(self, product_ids: list[str]):
        COUNTER.hit("products.products_by_ids_BATCH")
        await asyncio.sleep(HOP_SECONDS)
        by_id = {p["id"]: p for p in PRODUCTS}
        return [by_id.get(pid) for pid in product_ids]


class InventoryService:
    async def get_inventory(self, product_id: str):
        COUNTER.hit("inventory.get_inventory")
        await asyncio.sleep(HOP_SECONDS)
        return INVENTORY.get(product_id)


class NotificationService:
    async def notifications_for_user(self, user_id: str):
        COUNTER.hit("notifications.for_user")
        await asyncio.sleep(HOP_SECONDS)
        return [n for n in NOTIFICATIONS if n["user_id"] == user_id]
