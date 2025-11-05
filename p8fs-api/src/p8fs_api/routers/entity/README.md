# Entity routers

Entity routes are simple templated endpoints that use the same controller repository for a different model e.g. Resources or Moments in the p8fs models.

They should provider get by id or name, search, put and should all be tenant bound. The routes can be at api/entity/<entity_type>=
If the enity is 'public' namespace we omit the prefix other wise write <namespace>-<entity_name>