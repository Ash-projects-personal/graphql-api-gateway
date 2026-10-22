# How this works, in plain words

The gateway is a schema plus resolvers in front of five small
downstream stand ins. The interesting mechanics are the two loaders.
When a query asks for orders for 10 users, the naive resolver calls
the orders service 10 times. The batching loader instead collects the
10 user ids requested during the same execution tick and makes one
batched call. Same trick for products: 20 order lines ask for 4 unique
products, the loader dedupes them into one batched fetch, and the TTL
cache sits in front so repeats inside the TTL cost nothing. The
counters on the services are how I know this works: 31 downstream
calls naive, 3 batched, both from a cold cache. An earlier draft of
the benchmark forgot to clear the product cache between runs and the
loader appeared to need zero product calls; that was the cache leaking
across runs, and the benchmark now clears it and says so in a comment.

The latency result deserves the same care. Batching did not make the
local query faster in any meaningful way, because the stand ins answer
concurrently and the simulated hop is only 5 ms. What batching cuts is
downstream load, 31 calls to 3, and that is the claim I make. The
original repo claimed 320 ms down to 45 ms with no harness at all; a
number without a harness is just a sentence.

## What got re scoped from the original

The original could not start (no server file), could not resolve
products (no resolver), and called a Map a Redis cache. All three are
fixed by building the missing pieces rather than editing the words:
server.py exists, every root field has a passing query test, and the
cache is honestly labelled in-memory with a measured hit count from a
stated workload.
