"""Single source of truth for SQL identifiers that get interpolated into queries.

SQLite cannot parameterize table names, so the handful of queries that need a
dynamic table have to build the statement string themselves. Every such site
goes through quote_identifier() so the interpolated value is provably one of a
fixed set of names rather than whatever the caller happened to pass.
"""

# Whitelist of allowed table names to prevent SQL injection
ALLOWED_TABLES = {'projects', 'items', 'channels', 'llms', 'prompts', 'project_data', 'query_history', 'channel_tags', 'prompt_tags'}


def validate_table_name(table_name: str) -> str:
    """
    Validate that the table name is in the allowed whitelist.
    Raises ValueError if table name is not allowed. Returns the name unchanged.
    """
    if table_name not in ALLOWED_TABLES:
        raise ValueError(f"Invalid table name: {table_name}. Must be one of {ALLOWED_TABLES}")
    return table_name


def quote_identifier(table_name: str) -> str:
    """
    Validate a table name and return it quoted for interpolation into SQL.

    Use this anywhere a table name is placed into a query string:

        cursor.execute(f"SELECT id FROM {quote_identifier(table_name)}")
    """
    return f'"{validate_table_name(table_name)}"'
