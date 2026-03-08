#!/usr/bin/env bash
# =============================================================================
# factory_reset.sh — Destroys and rebuilds the Supabase database from scratch
# =============================================================================
# Usage: ./supabase/scripts/factory_reset.sh [--force]
#
# Prerequisites:
#   export SUPABASE_DB_URL="postgresql://postgres.XXXX:PASSWORD@aws-0-XX.pooler.supabase.com:5432/postgres"
#   (Supabase Dashboard → Settings → Database → Connection string → URI)
#
# Flow:
#   1. factory_drop.sql  → destroys all app schemas and objects
#   2. supabase db push  → re-applies all 42+ migrations
#   3. factory_seed.sql  → seeds categories, admins, gamification config
#
# If psql is not available, the script prints manual instructions instead.
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DROP_SQL="$SCRIPT_DIR/factory_drop.sql"
SEED_SQL="$SCRIPT_DIR/factory_seed.sql"
# supabase CLI must be run from the directory containing supabase/config.toml
SUPABASE_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# ─── Colors ──────────────────────────────────────────────────────────────────
RED='\033[0;31m'
YELLOW='\033[1;33m'
GREEN='\033[0;32m'
BOLD='\033[1m'
NC='\033[0m'

# ─── Parse arguments ─────────────────────────────────────────────────────────
FORCE=false
for arg in "$@"; do
    case $arg in
        --force) FORCE=true ;;
        *) echo -e "${RED}❌ Unknown argument: $arg${NC}"; exit 1 ;;
    esac
done

# ─── Validate required files ─────────────────────────────────────────────────
for f in "$DROP_SQL" "$SEED_SQL"; do
    if [ ! -f "$f" ]; then
        echo -e "${RED}❌ Required file not found: $f${NC}"
        exit 1
    fi
done

# ─── Validate environment variable ───────────────────────────────────────────
if [ -z "${SUPABASE_DB_URL:-}" ]; then
    echo -e "${RED}❌ SUPABASE_DB_URL is not set.${NC}"
    echo ""
    echo "Get it from: Supabase Dashboard → Settings → Database → Connection string → URI"
    echo ""
    echo "Then export it:"
    echo ""
    echo "  export SUPABASE_DB_URL=\"postgresql://postgres.XXXX:PASSWORD@aws-0-XX.pooler.supabase.com:5432/postgres\""
    echo ""
    exit 1
fi

# ─── Check psql availability ─────────────────────────────────────────────────
HAS_PSQL=false
if command -v psql &> /dev/null; then
    HAS_PSQL=true
fi

# ─── Confirmation prompt ─────────────────────────────────────────────────────
if [ "$FORCE" = false ]; then
    echo ""
    echo -e "${RED}${BOLD}⚠️  WARNING: This will PERMANENTLY DESTROY ALL DATA in the database.${NC}"
    echo ""
    echo "  Database: $SUPABASE_DB_URL"
    echo ""
    echo -n "  Type YES to continue (anything else aborts): "
    read -r CONFIRM
    if [ "$CONFIRM" != "YES" ]; then
        echo ""
        echo "Aborted. No changes were made."
        exit 0
    fi
fi

echo ""
echo "═══════════════════════════════════════════════════════════"
echo "  FACTORY RESET"
echo "═══════════════════════════════════════════════════════════"

# ─── No psql: print manual instructions ──────────────────────────────────────
if [ "$HAS_PSQL" = false ]; then
    echo ""
    echo -e "${YELLOW}⚠️  psql not found in PATH. Follow these manual steps:${NC}"
    echo ""
    echo "  Step 1 — Open Supabase SQL Editor and paste + run:"
    echo "           $DROP_SQL"
    echo ""
    echo "  Step 2 — Run from project root (oasis-backend/):"
    echo "           cd oasis-backend && supabase db push"
    echo ""
    echo "  Step 3 — Open Supabase SQL Editor and paste + run:"
    echo "           $SEED_SQL"
    echo ""
    echo "Install psql (macOS): brew install libpq && brew link --force libpq"
    echo ""
    exit 0
fi

# ─── Automated reset ─────────────────────────────────────────────────────────
echo ""
echo "[ 1/3 ] Dropping all schemas and objects (factory_drop.sql)..."
psql "$SUPABASE_DB_URL" --set ON_ERROR_STOP=on -f "$DROP_SQL"
echo -e "${GREEN}✅ Drop complete${NC}"

echo ""
echo "[ 2/3 ] Re-applying migrations (supabase db push)..."
cd "$SUPABASE_ROOT"
supabase db push
echo -e "${GREEN}✅ Migrations applied${NC}"

echo ""
echo "[ 3/3 ] Seeding initial data (factory_seed.sql)..."
psql "$SUPABASE_DB_URL" --set ON_ERROR_STOP=on -f "$SEED_SQL"
echo -e "${GREEN}✅ Seed complete${NC}"

echo ""
echo "═══════════════════════════════════════════════════════════"
echo -e "${GREEN}${BOLD}  ✅ Factory reset complete!${NC}"
echo "═══════════════════════════════════════════════════════════"
echo ""
