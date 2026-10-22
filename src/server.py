"""HTTP entry point: POST /graphql on 127.0.0.1:8941 (aiohttp)."""

import sys
from pathlib import Path

from aiohttp import web

sys.path.insert(0, str(Path(__file__).resolve().parent))

from gateway import SCHEMA, make_context
from graphql import graphql


async def handle(request: web.Request) -> web.Response:
    payload = await request.json()
    result = await graphql(
        SCHEMA,
        payload["query"],
        variable_values=payload.get("variables"),
        context_value=make_context(use_loader=True),
    )
    body = {"data": result.data}
    if result.errors:
        body["errors"] = [str(e) for e in result.errors]
    return web.json_response(body)


def make_app() -> web.Application:
    app = web.Application()
    app.router.add_post("/graphql", handle)
    return app


if __name__ == "__main__":
    web.run_app(make_app(), host="127.0.0.1", port=8941)
