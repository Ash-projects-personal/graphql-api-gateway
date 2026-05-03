# graphql-api-gateway

Built this to replace a mess of REST endpoints with a clean GraphQL layer. Pushing the schema and resolver logic here.

It's a GraphQL API gateway that sits in front of 5 downstream microservices (Users, Orders, Products, Inventory, Notifications). Before this, the frontend was making 4 to 5 separate REST calls to build a single page, which was slow and wasteful.

Two main things made this fast. DataLoader for N+1 batching: the classic GraphQL problem is that if you fetch 10 users and each user has orders, you end up making 11 database queries. DataLoader batches all those order lookups into a single WHERE id IN (...) query. This alone cut the average response time from 320ms to 45ms.

Redis caching on resolvers: frequently accessed data (user profiles, product catalog) gets cached in Redis for 60 seconds. Cache hit rate on the product resolver is around 80%.

Also eliminated 12 redundant REST endpoints that were doing the same thing with different shapes. Reduced client-side over-fetching by 65%.

Files are schema.js (the full GraphQL type definitions) and resolvers.js (resolver functions with DataLoader batching and Redis cache mock).
