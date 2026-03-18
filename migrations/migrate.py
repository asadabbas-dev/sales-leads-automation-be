"""
Migration: Add missing columns to the runs table.

Run this ONCE against your existing database:
    python migrate.py

It is safe to run multiple times — uses IF NOT EXISTS / DO NOTHING logic.
"""

import asyncio
import os
from urllib.parse import urlparse

from dotenv import load_dotenv  # pip install python-dotenv (only needed to run this script)

load_dotenv()  # reads your .env file

import asyncpg


async def migrate():
    database_url = os.environ.get("DATABASE_URL")
    if database_url:
        parsed = urlparse(database_url.replace("postgresql+asyncpg://", "postgresql://"))
        conn = await asyncpg.connect(
            host=parsed.hostname or "localhost",
            port=int(parsed.port or 5432),
            database=(parsed.path or "/")[1:] or "lead_ops",
            user=parsed.username or "postgres",
            password=parsed.password or "postgres",
        )
    else:
        conn = await asyncpg.connect(
            host=os.environ.get("DB_HOST", "localhost"),
            port=int(os.environ.get("DB_PORT", 5432)),
            database=os.environ.get("DB_NAME", "lead_ops"),
            user=os.environ.get("DB_USER", "postgres"),
            password=os.environ.get("DB_PASSWORD", "postgres"),
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

    # Add 'workflow' column if it doesn't exist
    await conn.execute("""
        ALTER TABLE runs
        ADD COLUMN IF NOT EXISTS workflow VARCHAR(64) DEFAULT NULL;
    """)
    print("  ✓ Column 'workflow' ensured.")

    # Add 'completed_at' column if it doesn't exist
    await conn.execute("""
        ALTER TABLE runs
        ADD COLUMN IF NOT EXISTS completed_at TIMESTAMPTZ DEFAULT NULL;
    """)
    print("  ✓ Column 'completed_at' ensured.")

    # Create leads table (must exist before runs.lead_id FK)
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS leads (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            idempotency_key VARCHAR(64) UNIQUE NOT NULL,
            name VARCHAR(255),
            email VARCHAR(255),
            phone VARCHAR(50),
            status VARCHAR(32) NOT NULL DEFAULT 'new',
            owner VARCHAR(255),
            next_action_at TIMESTAMPTZ,
            next_action_note TEXT,
            latest_run_id UUID,
            latest_score INTEGER,
            latest_qualified BOOLEAN,
            latest_source VARCHAR(255),
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
    """)
    print("  ✓ Table 'leads' ensured.")
    # Ensure follow-up columns exist (for leads created before 004)
    await conn.execute("""
        ALTER TABLE leads
        ADD COLUMN IF NOT EXISTS next_action_at TIMESTAMPTZ,
        ADD COLUMN IF NOT EXISTS next_action_note TEXT;
    """)
    print("  ✓ Columns 'leads.next_action_at' and 'leads.next_action_note' ensured.")
    await conn.execute("CREATE INDEX IF NOT EXISTS idx_leads_idempotency_key ON leads(idempotency_key);")
    await conn.execute("CREATE INDEX IF NOT EXISTS idx_leads_email ON leads(email);")
    await conn.execute("CREATE INDEX IF NOT EXISTS idx_leads_phone ON leads(phone);")
    await conn.execute("CREATE INDEX IF NOT EXISTS idx_leads_status ON leads(status);")

    # Add lead_id to runs (FK to leads)
    await conn.execute("""
        ALTER TABLE runs
        ADD COLUMN IF NOT EXISTS lead_id UUID REFERENCES leads(id);
    """)
    print("  ✓ Column 'runs.lead_id' ensured.")
    await conn.execute("CREATE INDEX IF NOT EXISTS idx_runs_lead_id ON runs(lead_id);")

    # ICP: leads.icp_score and company_profile table (005)
    await conn.execute("ALTER TABLE leads ADD COLUMN IF NOT EXISTS icp_score INTEGER;")
    print("  ✓ Column 'leads.icp_score' ensured.")
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS company_profile (
            id INTEGER PRIMARY KEY DEFAULT 1 CHECK (id = 1),
            industry VARCHAR(255),
            company_size VARCHAR(64),
            budget_min NUMERIC,
            budget_max NUMERIC,
            intent_keywords JSONB DEFAULT '[]',
            location VARCHAR(255),
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
    """)
    print("  ✓ Table 'company_profile' ensured.")
    await conn.execute("""
        INSERT INTO company_profile (id, industry, company_size, budget_min, budget_max, intent_keywords, location, updated_at)
        SELECT 1, NULL, NULL, NULL, NULL, '[]', NULL, now()
        WHERE NOT EXISTS (SELECT 1 FROM company_profile WHERE id = 1);
    """)
    print("  ✓ company_profile row ensured.")

    # Opportunities pipeline (application.md schema)
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS opportunities (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            title VARCHAR(512) NOT NULL,
            source VARCHAR(64) NOT NULL,
            deadline DATE,
            funding_value NUMERIC(14,2),
            description TEXT,
            url VARCHAR(2048),
            organization VARCHAR(512),
            location VARCHAR(255),
            industry_tags JSONB DEFAULT '[]',
            status VARCHAR(32) NOT NULL DEFAULT 'new',
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
    """)
    print("  ✓ Table 'opportunities' ensured.")
    await conn.execute("CREATE INDEX IF NOT EXISTS idx_opportunities_source ON opportunities(source);")
    await conn.execute("CREATE INDEX IF NOT EXISTS idx_opportunities_status ON opportunities(status);")
    await conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_opportunities_url_unique ON opportunities(url) WHERE url IS NOT NULL;")

    await conn.execute("""
        CREATE TABLE IF NOT EXISTS ai_analysis (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            opportunity_id UUID NOT NULL REFERENCES opportunities(id) ON DELETE CASCADE,
            industry_match JSONB DEFAULT '[]',
            proposal_complexity VARCHAR(64),
            success_probability DOUBLE PRECISION,
            recommended_company_size VARCHAR(64),
            key_requirements JSONB DEFAULT '[]',
            raw_response JSONB,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
    """)
    print("  ✓ Table 'ai_analysis' ensured.")
    await conn.execute("CREATE INDEX IF NOT EXISTS idx_ai_analysis_opportunity_id ON ai_analysis(opportunity_id);")

    await conn.execute("""
        CREATE TABLE IF NOT EXISTS opportunity_scores (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            opportunity_id UUID NOT NULL REFERENCES opportunities(id) ON DELETE CASCADE,
            score INTEGER NOT NULL,
            priority VARCHAR(64),
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
    """)
    print("  ✓ Table 'opportunity_scores' ensured.")
    await conn.execute("CREATE INDEX IF NOT EXISTS idx_opportunity_scores_opportunity_id ON opportunity_scores(opportunity_id);")

    await conn.execute("""
        CREATE TABLE IF NOT EXISTS crm_records (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            opportunity_id UUID NOT NULL REFERENCES opportunities(id) ON DELETE CASCADE,
            stage VARCHAR(64) NOT NULL,
            assigned_user VARCHAR(255),
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
    """)
    print("  ✓ Table 'crm_records' ensured.")
    await conn.execute("CREATE INDEX IF NOT EXISTS idx_crm_records_opportunity_id ON crm_records(opportunity_id);")
    await conn.execute("CREATE INDEX IF NOT EXISTS idx_crm_records_stage ON crm_records(stage);")

    await conn.close()
    print("\nMigration complete. You can now restart your FastAPI server.")


if __name__ == "__main__":
    asyncio.run(migrate())