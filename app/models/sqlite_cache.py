# app/models/sqlite_db.py

import aiosqlite

# Shared In-Memory Database
DB_URL = "file:shared_memory_db?mode=memory&cache=shared"

# Global connection instance
db_connection: aiosqlite.Connection = None


### 🚀 Initialize the Shared Database Connection
async def init_db():
    """Initialize the SQLite shared in-memory database and set up default tables."""
    global db_connection
    if db_connection is None:
        db_connection = await aiosqlite.connect(DB_URL, uri=True)         
        await db_connection.execute("PRAGMA journal_mode=WAL;")
        await db_connection.execute("PRAGMA synchronous=NORMAL;")
        await db_connection.execute("""
            CREATE TABLE IF NOT EXISTS cache (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        await db_connection.commit()


async def check_db_mode():
    result = {}

    async with db_connection.execute("PRAGMA journal_mode;") as cursor:
        journal_mode = await cursor.fetchone()
        result['journal_mode'] = journal_mode[0] if journal_mode else None

    async with db_connection.execute("PRAGMA database_list;") as cursor:
        database_list = await cursor.fetchall()
        result['database_list'] = database_list if database_list else []

    return result




### 🚀 Close the Shared Database Connection
async def close_db():
    """Close the shared SQLite database connection."""
    global db_connection
    if db_connection:
        await db_connection.close()
        db_connection = None


### 🚀 Key-Value Cache Operations
async def set_cache(key: str, value: str):
    """Set a key-value pair in the cache."""
    await db_connection.execute(
        "INSERT OR REPLACE INTO cache (key, value) VALUES (?, ?)", 
        (key, value)
    )
    await db_connection.commit()


async def get_cache(key: str):
    """Get a value from the cache by key."""
    async with db_connection.execute(
        "SELECT value FROM cache WHERE key = ?", 
        (key,)
    ) as cursor:
        result = await cursor.fetchone()
        return result[0] if result else None


### 🚀 Relational Table Operations
async def create_table(table_name: str, schema: str):
    """
    Create a dynamic relational table.
    Args:
        table_name (str): Name of the table.
        schema (str): SQL schema definition (e.g., 'id INTEGER PRIMARY KEY, name TEXT').
    """
    query = f"CREATE TABLE IF NOT EXISTS {table_name} ({schema})"
    await db_connection.execute(query)
    await db_connection.commit()


async def insert_into_table(table_name: str, columns: list[str], values: list):
    """
    Insert a row into a dynamic table.
    Args:
        table_name (str): Table to insert into.
        columns (list): Column names.
        values (list): Corresponding values.
    """
    placeholders = ", ".join(["?" for _ in columns])
    column_names = ", ".join(columns)
    query = f"INSERT INTO {table_name} ({column_names}) VALUES ({placeholders})"
    await db_connection.execute(query, values)
    await db_connection.commit()


async def get_from_table(table_name: str, criteria: str = "", params: tuple = ()):
    """
    Get rows from a table based on criteria.
    Args:
        table_name (str): Table name.
        criteria (str): WHERE condition (e.g., "id = ?").
        params (tuple): Values for WHERE clause.
    """
    query = f"SELECT * FROM {table_name}"
    if criteria:
        query += f" WHERE {criteria}"
    async with db_connection.execute(query, params) as cursor:
        return await cursor.fetchall()


async def update_table(table_name: str, updates: str, criteria: str = "", params: tuple = ()):
    """
    Update rows in a table.
    Args:
        table_name (str): Table name.
        updates (str): Update string (e.g., "name = ?, email = ?").
        criteria (str): WHERE condition.
        params (tuple): Values for updates and criteria.
    """
    query = f"UPDATE {table_name} SET {updates}"
    if criteria:
        query += f" WHERE {criteria}"
    await db_connection.execute(query, params)
    await db_connection.commit()


async def delete_from_table(table_name: str, criteria: str, params: tuple):
    """
    Delete rows from a table.
    Args:
        table_name (str): Table name.
        criteria (str): WHERE condition.
        params (tuple): Values for criteria.
    """
    query = f"DELETE FROM {table_name} WHERE {criteria}"
    await db_connection.execute(query, params)
    await db_connection.commit()
