#!/usr/bin/env bash
# =============================================================================
# factory_reset.sh — Destroys and rebuilds the Supabase database from scratch
# =============================================================================
# Usage: ./supabase/scripts/factory_reset.sh [--env dev|staging|production] [--force]
#
# Environment selection:
#   --env dev         → loads .env.dev (default)
#   --env staging     → loads .env.staging
#   --env production  → loads .env.production (requires explicit confirmation)
#
# Flow:
#   1. factory_drop.sql  → destroys all app schemas and objects
#   2. supabase db push  → re-applies all migrations (uses --db-url for portability)
#   3. factory_seed.sql  → seeds categories, admins, gamification config
#
# Safety:
#   - Production project ref is hardcoded as PROTECTED — cannot be wiped without
#     --env production AND typing the full project ref as confirmation.
#   - --force skips the normal confirmation prompt but NEVER bypasses prod protection.
#   - Passwords are masked in all prompts and logs.
#
# If psql is not available, the script prints manual instructions instead.
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DROP_SQL="$SCRIPT_DIR/factory_drop.sql"
SEED_SQL="$SCRIPT_DIR/factory_seed.sql"
# supabase CLI must be run from the directory containing supabase/config.toml
SUPABASE_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# ─── Protected production project refs ──────────────────────────────────────
# Add any Supabase project refs that should NEVER be wiped without explicit
# --env production + confirmation with the full project ref.
PROTECTED_REFS="iwhbcqamkiscyjydgndg"

# ─── Colors ──────────────────────────────────────────────────────────────────
RED='\033[0;31m'
YELLOW='\033[1;33m'
GREEN='\033[0;32m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

# ─── Helper: extract project ref from SUPABASE_DB_URL ───────────────────────
# Format: postgresql://postgres.<REF>:<PASSWORD>@<HOST>:<PORT>/<DB>
extract_project_ref() {
    local url="$1"
    echo "$url" | sed -n 's|.*postgres\.\([^:]*\):.*|\1|p'
}

# ─── Helper: mask password in a URL for safe display ────────────────────────
mask_url() {
    local url="$1"
    echo "$url" | sed 's|:\([^@]*\)@|:****@|'
}

# ─── Helper: check if a ref is protected ────────────────────────────────────
is_protected_ref() {
    local ref="$1"
    for protected in $PROTECTED_REFS; do
        if [ "$ref" = "$protected" ]; then
            return 0
        fi
    done
    return 1
}

# ─── Parse arguments ─────────────────────────────────────────────────────────
FORCE=false
ENV_NAME="dev"
SKIP_NEXT=false
ARGS=("$@")
for i in "${!ARGS[@]}"; do
    if [ "$SKIP_NEXT" = true ]; then
        SKIP_NEXT=false
        continue
    fi
    case "${ARGS[$i]}" in
        --force) FORCE=true ;;
        --env)
            next_idx=$((i + 1))
            if [ $next_idx -lt ${#ARGS[@]} ]; then
                ENV_NAME="${ARGS[$next_idx]}"
                SKIP_NEXT=true
            else
                echo -e "${RED}❌ --env requires a value: dev, staging, or production${NC}"
                exit 1
            fi
            ;;
        *)
            echo -e "${RED}❌ Unknown argument: ${ARGS[$i]}${NC}"
            echo "Usage: $0 [--env dev|staging|production] [--force]"
            exit 1
            ;;
    esac
done

# Validate env name
case $ENV_NAME in
    dev|staging|production) ;;
    *)
        echo -e "${RED}❌ Invalid environment: $ENV_NAME${NC}"
        echo "Valid values: dev, staging, production"
        exit 1 ;;
esac

echo ""
echo -e "${CYAN}🔧 Environment: ${BOLD}$ENV_NAME${NC}"

# ─── Validate required files ────────────────────────────────────────────────
for f in "$DROP_SQL" "$SEED_SQL"; do
    if [ ! -f "$f" ]; then
        echo -e "${RED}❌ Required file not found: $f${NC}"
        exit 1
    fi
done

# ─── Load .env.{env} if SUPABASE_DB_URL not already in environment ──────────
if [ -z "${SUPABASE_DB_URL:-}" ]; then
    ENV_FILE="$SUPABASE_ROOT/.env.${ENV_NAME}"
    if [ -f "$ENV_FILE" ]; then
        SUPABASE_DB_URL=$(grep -E '^SUPABASE_DB_URL=' "$ENV_FILE" | head -1 | cut -d '=' -f2- | tr -d '"' | tr -d "'")
        if [ -n "$SUPABASE_DB_URL" ]; then
            echo -e "${YELLOW}ℹ️  Loaded SUPABASE_DB_URL from $ENV_FILE${NC}"
            export SUPABASE_DB_URL
        fi
    else
        echo -e "${RED}❌ Environment file not found: $ENV_FILE${NC}"
        echo ""
        echo "Create it with the required variables. See .env.example for the template."
        echo ""
        exit 1
    fi
fi

# ─── Validate environment variable ──────────────────────────────────────────
if [ -z "${SUPABASE_DB_URL:-}" ]; then
    echo -e "${RED}❌ SUPABASE_DB_URL is not set and not found in .env.${ENV_NAME}${NC}"
    echo ""
    echo "Add it to oasis-backend/.env.${ENV_NAME}:"
    echo ""
    echo "  SUPABASE_DB_URL=postgresql://postgres.XXXX:PASSWORD@aws-0-XX.pooler.supabase.com:5432/postgres"
    echo ""
    echo "Get the URL from: Supabase Dashboard → Settings → Database → Connection string → URI (Session mode)"
    echo ""
    exit 1
fi

# ─── Production protection ──────────────────────────────────────────────────
PROJECT_REF=$(extract_project_ref "$SUPABASE_DB_URL")
MASKED_URL=$(mask_url "$SUPABASE_DB_URL")

if [ -n "$PROJECT_REF" ] && is_protected_ref "$PROJECT_REF"; then
    if [ "$ENV_NAME" != "production" ]; then
        echo ""
        echo -e "${RED}${BOLD}🚫 BLOCKED: Protected production database detected!${NC}"
        echo ""
        echo "  Project ref: $PROJECT_REF"
        echo "  Database:    $MASKED_URL"
        echo ""
        echo "  You are trying to run factory reset against a PRODUCTION database"
        echo "  without using --env production."
        echo ""
        echo "  If this is intentional, re-run with:"
        echo "    $0 --env production"
        echo ""
        echo "  If this is a mistake, create a .env.dev file with your dev database URL."
        echo ""
        exit 1
    fi

    # Even with --env production, require typing the full project ref
    # --force does NOT bypass this check
    echo ""
    echo -e "${RED}${BOLD}🚨 PRODUCTION DATABASE — DESTRUCTIVE OPERATION 🚨${NC}"
    echo ""
    echo "  This will ${RED}PERMANENTLY DESTROY ALL DATA${NC} in:"
    echo ""
    echo "  Project ref: ${BOLD}$PROJECT_REF${NC}"
    echo "  Database:    $MASKED_URL"
    echo ""
    echo -e "  ${YELLOW}--force does NOT bypass this check. This is your last safeguard.${NC}"
    echo ""
    echo -n "  Type the full project ref ($PROJECT_REF) to confirm: "
    read -r CONFIRM_REF
    if [ "$CONFIRM_REF" != "$PROJECT_REF" ]; then
        echo ""
        echo "  Aborted. Project ref did not match."
        exit 0
    fi
    echo ""
    echo -e "${RED}  ⚠️  Proceeding with PRODUCTION factory reset...${NC}"
fi

# ─── Check psql availability ────────────────────────────────────────────────
HAS_PSQL=false
if command -v psql &> /dev/null; then
    HAS_PSQL=true
fi

# ─── Normal confirmation prompt (non-prod, non-force) ───────────────────────
if [ "$FORCE" = false ]; then
    # Skip if we already confirmed for production above
    if [ -z "$PROJECT_REF" ] || ! is_protected_ref "$PROJECT_REF"; then
        echo ""
        echo -e "${RED}${BOLD}⚠️  WARNING: This will PERMANENTLY DESTROY ALL DATA in the database.${NC}"
        echo ""
        echo "  Environment: $ENV_NAME"
        echo "  Database:    $MASKED_URL"
        echo ""
        echo -n "  Type YES to continue (anything else aborts): "
        read -r CONFIRM
        if [ "$CONFIRM" != "YES" ]; then
            echo ""
            echo "  Aborted. No changes were made."
            exit 0
        fi
    fi
fi

echo ""
echo "═══════════════════════════════════════════════════════════"
echo "  FACTORY RESET ($ENV_NAME)"
echo "═══════════════════════════════════════════════════════════"

# ─── No psql: print manual instructions ─────────────────────────────────────
if [ "$HAS_PSQL" = false ]; then
    echo ""
    echo -e "${YELLOW}⚠️  psql not found in PATH. Follow these manual steps:${NC}"
    echo ""
    echo "  Step 1 — Open Supabase SQL Editor and paste + run:"
    echo "           $DROP_SQL"
    echo ""
    echo "  Step 2 — Run from project root (oasis-backend/):"
    echo "           cd oasis-backend && supabase db push --db-url \"\$SUPABASE_DB_URL\""
    echo ""
    echo "  Step 3 — Open Supabase SQL Editor and paste + run:"
    echo "           $SEED_SQL"
    echo ""
    echo "Install psql (macOS): brew install libpq && brew link --force libpq"
    echo ""
    exit 0
fi

# ─── Automated reset ────────────────────────────────────────────────────────
echo ""
echo "[ 1/3 ] Dropping all schemas and objects (factory_drop.sql)..."
psql "$SUPABASE_DB_URL" --set ON_ERROR_STOP=on -f "$DROP_SQL"
echo -e "${GREEN}✅ Drop complete${NC}"

echo ""
echo "[ 2/3 ] Re-applying migrations (supabase db push --db-url)..."
cd "$SUPABASE_ROOT"
supabase db push --db-url "$SUPABASE_DB_URL"
echo -e "${GREEN}✅ Migrations applied${NC}"

echo ""
echo "[ 3/3 ] Seeding initial data (factory_seed.sql)..."
psql "$SUPABASE_DB_URL" --set ON_ERROR_STOP=on -f "$SEED_SQL"
echo -e "${GREEN}✅ Seed complete${NC}"

echo ""
echo "═══════════════════════════════════════════════════════════"
echo -e "${GREEN}${BOLD}  ✅ Factory reset complete! ($ENV_NAME)${NC}"
echo "═══════════════════════════════════════════════════════════"
echo ""
