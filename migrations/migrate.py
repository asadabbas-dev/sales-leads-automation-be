"""
Migration: Add missing columns to the runs table.

Run this ONCE against your existing database:
    python migrate.py

It is safe to run multiple times — uses IF NOT EXISTS / DO NOTHING logic.
"""

import asyncio
import os
from dotenv import load_dotenv  # pip install python-dotenv  (only needed to run this script)

load_dotenv()  # reads your .env file

import asyncpg


async def migrate():
    conn = await asyncpg.connect(
        host=os.environ["DB_HOST"],
        port=int(os.environ.get("DB_PORT", 5432)),
        database=os.environ["DB_NAME"],
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
    )

    print("Connected to database. Running migration...")

    # Add 'priority' column if it doesn't exist
    await conn.execute("""
        ALTER TABLE runs
        ADD COLUMN IF NOT EXISTS priority VARCHAR(20) DEFAULT NULL;
    """)
    print("  ✓ Column 'priority' ensured.")

    # Add 'scheduled_at' column if it doesn't exist
    await conn.execute("""
        ALTER TABLE runs
        ADD COLUMN IF NOT EXISTS scheduled_at VARCHAR(50) DEFAULT NULL;
    """)
    print("  ✓ Column 'scheduled_at' ensured.")

    await conn.close()
    print("\nMigration complete. You can now restart your FastAPI server.")


if __name__ == "__main__":
    asyncio.run(migrate())