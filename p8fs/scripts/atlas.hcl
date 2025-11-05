# Atlas configuration for P8FS

env "local" {
  # Exclude system schemas and extension schemas
  # Atlas will manage all other schemas by default
  exclude = ["information_schema", "pg_*", "ag_catalog"]
}