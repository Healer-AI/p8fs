"""
Schema synchronization utilities for tests.

Ensures database tables match Pydantic model definitions without manual ALTER TABLE statements.
"""

from typing import Type
from p8fs.models.base import AbstractModel
from p8fs.providers import BaseSQLProvider
from p8fs_cluster.logging import get_logger

logger = get_logger(__name__)


def sync_table_schema(provider: BaseSQLProvider, model_class: Type[AbstractModel]) -> dict[str, list[str]]:
    """
    Synchronize database table schema with Pydantic model definition.

    Introspects the model's fields and ensures the database table has all required columns.
    This is useful for tests where the model may have evolved but migrations haven't run.

    Args:
        provider: Database provider
        model_class: Pydantic model class to sync

    Returns:
        Dict with 'added' and 'skipped' column lists

    Example:
        from p8fs.models.p8 import Resources
        from p8fs.providers import get_provider

        provider = get_provider()
        provider.connect_sync()

        result = sync_table_schema(provider, Resources)
        # result = {'added': ['updated_at', 'summary'], 'skipped': ['id', 'name']}
    """
    schema = model_class.to_sql_schema()
    table_name = schema['table_name']
    fields = schema.get('fields', {})

    # Get existing columns from database
    existing_columns = _get_existing_columns(provider, table_name)

    added = []
    skipped = []

    for col_name, col_def in fields.items():
        if col_name in existing_columns:
            skipped.append(col_name)
            continue

        # Add missing column - use sql_type from schema
        sql_type = col_def.get('sql_type', 'TEXT')
        nullable = col_def.get('nullable', True)

        # Build ALTER TABLE statement
        alter_sql = f"ALTER TABLE {table_name} ADD COLUMN IF NOT EXISTS {col_name} {sql_type}"

        if not nullable:
            alter_sql += " NOT NULL"

        # Handle defaults based on SQL type
        if 'default' in col_def and col_def['default'] is not None:
            default = col_def['default']
            if isinstance(default, str):
                alter_sql += f" DEFAULT '{default}'"
            elif isinstance(default, (dict, list)):
                import json
                alter_sql += f" DEFAULT '{json.dumps(default)}'"
            else:
                alter_sql += f" DEFAULT {default}"
        elif col_def.get('is_json'):
            # JSONB fields need default
            alter_sql += " DEFAULT '{}'"

        try:
            provider.execute(alter_sql)
            added.append(col_name)
            logger.info(f"Added column {table_name}.{col_name} ({sql_type})")
        except Exception as e:
            logger.warning(f"Failed to add column {col_name}: {e}")

    return {'added': added, 'skipped': skipped}


def _get_existing_columns(provider: BaseSQLProvider, table_name: str) -> set[str]:
    """Get set of existing column names from database table."""
    try:
        # PostgreSQL information_schema query
        result = provider.execute(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = %s
            """,
            (table_name,)
        )
        return {row['column_name'] for row in result}
    except Exception as e:
        logger.warning(f"Could not introspect table {table_name}: {e}")
        return set()


def ensure_system_fields(provider: BaseSQLProvider, table_name: str) -> None:
    """
    Ensure common system fields exist on a table.

    Adds: created_at, updated_at if missing.

    Args:
        provider: Database provider
        table_name: Table to update
    """
    system_fields = {
        'created_at': 'TIMESTAMP DEFAULT NOW()',
        'updated_at': 'TIMESTAMP DEFAULT NOW()',
    }

    existing = _get_existing_columns(provider, table_name)

    for field_name, field_def in system_fields.items():
        if field_name not in existing:
            try:
                provider.execute(
                    f"ALTER TABLE {table_name} ADD COLUMN IF NOT EXISTS {field_name} {field_def}"
                )
                logger.info(f"Added system field {table_name}.{field_name}")
            except Exception as e:
                logger.warning(f"Failed to add {field_name}: {e}")
