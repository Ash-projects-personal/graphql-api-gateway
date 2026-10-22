# GraphQL API Gateway

I built this to explore replacing a mess of REST endpoints with one
GraphQL layer. The first version of this repo was mostly a claim: a
schema with no server, product fields with no resolvers, a JavaScript
Map described as Redis, and response times quoted from nowhere. This
rebuild keeps the idea and makes every piece of it run.

## What runs now

- A real server: `src/server.py` serves POST /graphql on localhost
  (aiohttp plus graphql-core). The original repo had a start script
  pointing at a server file that did not exist.
- Resolvers for every schema field across five domains: users, orders,
  products, inventory, notifications. Products and inventory resolve
  now; in the original they were declared in the schema and silently
  absent from the resolvers.
- The downstream services are local in-process stand ins with small
  datasets, a 5 ms simulated network hop, and call counters. They are
  not real microservices and the README does not call them that. The
  counters exist so the gateway claims are numbers.

## Measured results (outputs/metrics.json)

The page query (10 users, each with their orders and product names),
cold cache both ways:

- Without batching: 31 downstream calls (1 user list, 10 per user
  order lookups, 20 product lookups).
- With the DataLoader style batching loader: 3 downstream calls (1
  user list, 1 batched orders call, 1 batched products call).
- Latency on this machine barely moved: mean 14.34 ms with the loader
  versus 15.00 ms without, over 25 runs each. The simulated hops run
  concurrently either way, so locally the win is call count, not wall
  clock. Against real services with sequential network round trips,
  call count is what turns into latency, but I am reporting what I
  measured here, not that extrapolation.
- Product cache: an in-memory TTL cache in the gateway process, 60
  second TTL. Twenty repeats of the same product query scored 19 hits
  and 1 miss, counted by the cache itself. It is not Redis. The
  original README said Redis while using a Map; this one says
  in-memory because that is what it is.
- Every root field was queried and resolved: user, users, order,
  orders, product, products, inventory, notifications.

## Deleted claims from the original

- "Reduced response time from 320ms to 45ms": no benchmark ever
  existed. Deleted.
- "Cache hit rate on the product resolver around 80%": there was no
  product resolver and no metrics. Deleted. The measured hit rate
  above replaces the genre of claim, with the workload stated.
- "Eliminated 12 redundant REST endpoints" and "reduced over-fetching
  by 65%": unverifiable from anything in the repo. Deleted. The honest
  version is the standard one: GraphQL lets clients request only the
  fields they need instead of fixed REST payload shapes.

## Run it

```
python3 src/server.py        # POST /graphql on 127.0.0.1:8941
python3 src/benchmark.py     # writes outputs/metrics.json
pytest tests/
```
