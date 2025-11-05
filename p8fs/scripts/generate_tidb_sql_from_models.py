#!/usr/bin/env python3
"""
Generate TiDB SQL migration from Python models in p8fs.models.p8.

This script reads all AbstractModel subclasses from p8fs.models.p8 and generates
complete TiDB migration SQL with proper VECTOR and JSON types.
"""

import sys
from pathlib import Path

def generate_migration_sql():
    """Generate TiDB migration SQL from p8fs.models.p8 models."""
    # Import models and provider
    try:
        from p8fs.models.p8 import (
            Agent, ApiProxy, Error, Files, Function, Job,
            LanguageModelApi, Project, Resources, Session, Task,
            Tenant, TokenUsage, User, KVStorage
        )
        from p8fs.providers.tidb import TiDBProvider
    except ImportError as e:
        print(f"❌ Failed to import required modules: {e}", file=sys.stderr)
        return False

    provider = TiDBProvider()

    # List of all models to generate
    models = [
        Agent, ApiProxy, Error, Files, Function, Job,
        LanguageModelApi, Project, Resources, Session, Task,
        Tenant, TokenUsage, User, KVStorage
    ]

    # Generate header with TiDB-specific setup
    sql_lines = [
        "-- P8FS Full TiDB Migration Script",
        "-- Generated from Python models with TiDB-specific types",
        "--",
        "-- This migration creates tables in a 'public' database to match PostgreSQL's",
        "-- public schema structure. This makes it easier to compare and switch between",
        "-- PostgreSQL and TiDB deployments.",
        "--",
        "-- Structure:",
        "--   - Main tables: public.agents, public.users, etc.",
        "--   - Embedding tables: embeddings.agents_embeddings, etc.",
        "--",
        "-- Connection string: mysql://root@localhost:4000/public",
        "",
        "-- Create public database to match PostgreSQL structure",
        "CREATE DATABASE IF NOT EXISTS `public`;",
        "USE `public`;",
        "",
        "-- Create embeddings database (TiDB uses database instead of schema)",
        "CREATE DATABASE IF NOT EXISTS embeddings;",
        "",
        "-- Helper function for updated_at trigger (TiDB uses ON UPDATE CURRENT_TIMESTAMP)",
        "-- Note: TiDB automatically handles updated_at with ON UPDATE CURRENT_TIMESTAMP",
        "",
        "-- KV Entity Mapping Table for reverse key lookups",
        provider.create_kv_mapping_table_sql(),
        ""
    ]

    # Generate SQL for each model
    for model in models:
        try:
            # Add model comment
            sql_lines.append(f"-- {model.__name__} Model")

            # Generate table creation SQL
            table_sql = provider.create_table_sql(model)
            sql_lines.append(table_sql)
            sql_lines.append("")

            # Generate embedding table if needed
            embedding_sql = provider.create_embedding_table_sql(model)
            if embedding_sql.strip():
                sql_lines.append(embedding_sql)
                sql_lines.append("")

        except Exception as e:
            print(f"❌ Failed to generate SQL for {model.__name__}: {e}", file=sys.stderr)
            import traceback
            traceback.print_exc()
            return False

    # Write to migration file
    script_dir = Path(__file__).parent
    repo_root = script_dir.parent
    output_file = repo_root / "extensions" / "migrations" / "tidb" / "install.sql"

    # Ensure directory exists
    output_file.parent.mkdir(parents=True, exist_ok=True)

    # Write the SQL
    full_sql = "\n".join(sql_lines)
    output_file.write_text(full_sql)

    print(f"✅ Generated TiDB migration SQL for {len(models)} models")
    print(f"   Output: {output_file}")
    print(f"   Size: {len(full_sql):,} characters")

    # Show key field validation
    print("\n📋 Key field validation:")
    for model in models:
        key_field = model.get_model_key_field()
        print(f"   {model.__name__:20} -> {key_field}")

    return True


def main():
    """Main entry point."""
    print("🔄 Generating TiDB SQL migration from Python models...")

    success = generate_migration_sql()

    if success:
        print("\n🎉 TiDB SQL generation completed successfully!")
        sys.exit(0)
    else:
        print("\n❌ TiDB SQL generation failed!")
        sys.exit(1)


if __name__ == "__main__":
    main()
