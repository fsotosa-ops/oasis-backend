#!/bin/bash
set -e

# ==============================================================================
# CONFIGURACIÓN INICIAL
# Edita estas variables o déjalas así para el entorno de Desarrollo
# ==============================================================================
PROJECT_ID="fsummer-oasis-dev"
PROJECT_NAME="OASIS Platform (Dev)"
GITHUB_ORG="fsotosa-ops"
GITHUB_REPO="oasis-backend"
REGION="us-central1"

# Colores para output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${GREEN}🚀 Iniciando configuración completa para: $PROJECT_ID${NC}"

# 1. CREACIÓN Y SELECCIÓN DEL PROYECTO
echo -e "\n${YELLOW}[1/6] Verificando proyecto...${NC}"
if gcloud projects describe "$PROJECT_ID" &>/dev/null; then
    echo "✅ El proyecto $PROJECT_ID ya existe."
else
    echo "Creando proyecto $PROJECT_ID..."
    gcloud projects create "$PROJECT_ID" --name="$PROJECT_NAME"
fi

# IMPORTANTE: Cambiar el contexto de la terminal al nuevo proyecto
echo "Seteando proyecto activo en gcloud..."
gcloud config set project "$PROJECT_ID"

# 2. VINCULACIÓN DE FACTURACIÓN (BILLING)
echo -e "\n${YELLOW}[2/6] Verificando facturación...${NC}"
BILLING_ENABLED=$(gcloud beta billing projects describe "$PROJECT_ID" --format="value(billingEnabled)")

if [ "$BILLING_ENABLED" != "true" ]; then
    echo -e "${RED}⚠️  El proyecto no tiene facturación vinculada.${NC}"
    echo "Listando cuentas de facturación disponibles:"
    gcloud beta billing accounts list --format="table(displayName, name, open)"
    
    echo -e "\n${YELLOW}Por favor, copia el ACCOUNT_ID (ej. 012345-6789AB-CDEF01) de la lista de arriba:${NC}"
    read -r BILLING_ID
    
    if [ -n "$BILLING_ID" ]; then
        gcloud beta billing projects link "$PROJECT_ID" --billing-account="$BILLING_ID"
        echo "✅ Facturación vinculada correctamente."
    else
        echo -e "${RED}❌ No se ingresó ID. Las APIs fallarán sin facturación.${NC}"
        exit 1
    fi
else
    echo "✅ El proyecto ya tiene facturación habilitada."
fi

# 3. HABILITAR APIS
echo -e "\n${YELLOW}[3/6] Habilitando APIs (esto puede tardar unos minutos)...${NC}"
gcloud services enable \
    run.googleapis.com \
    artifactregistry.googleapis.com \
    secretmanager.googleapis.com \
    iamcredentials.googleapis.com \
    cloudresourcemanager.googleapis.com \
    iam.googleapis.com

# 4. CREAR REPOSITORIO DE ARTIFACT REGISTRY
echo -e "\n${YELLOW}[4/6] Configurando Artifact Registry...${NC}"
REPO_NAME="oasis-api"
if ! gcloud artifacts repositories describe "$REPO_NAME" --location="$REGION" &>/dev/null; then
    gcloud artifacts repositories create "$REPO_NAME" \
        --repository-format=docker \
        --location="$REGION" \
        --description="OASIS Platform Docker Repository"
    echo "✅ Repositorio creado."
else
    echo "✅ El repositorio ya existe."
fi

# 5. CREAR SECRETOS EN SECRET MANAGER
echo -e "\n${YELLOW}[5/6] Creando secretos en Secret Manager...${NC}"

ENV_FILE=".env"
if [ ! -f "$ENV_FILE" ]; then
    echo -e "${RED}❌ No se encontró archivo .env. Crea uno con las variables de Supabase.${NC}"
    exit 1
fi

SECRETS=("SUPABASE_URL" "SUPABASE_ANON_KEY" "SUPABASE_SERVICE_ROLE_KEY" "SUPABASE_JWKS_URL" "SUPERSET_URL" "SUPERSET_ADMIN_USERNAME" "SUPERSET_ADMIN_PASSWORD" "SUPERSET_DASHBOARD_ID")

for SECRET_NAME in "${SECRETS[@]}"; do
    SECRET_VALUE=$(grep "^${SECRET_NAME}=" "$ENV_FILE" | cut -d'=' -f2-)

    if [ -z "$SECRET_VALUE" ]; then
        echo -e "${RED}⚠️  $SECRET_NAME no encontrada en .env, saltando.${NC}"
        continue
    fi

    if ! gcloud secrets describe "$SECRET_NAME" &>/dev/null; then
        printf "%s" "$SECRET_VALUE" | gcloud secrets create "$SECRET_NAME" \
            --data-file=- \
            --replication-policy="automatic"
        echo "✅ Secreto $SECRET_NAME creado."
    else
        printf "%s" "$SECRET_VALUE" | gcloud secrets versions add "$SECRET_NAME" --data-file=-
        echo "✅ Secreto $SECRET_NAME actualizado (nueva versión)."
    fi
done

# 6. CONFIGURAR WORKLOAD IDENTITY FEDERATION (WIF)
echo -e "\n${YELLOW}[6/6] Configurando Seguridad (WIF & Service Account)...${NC}"
SA_NAME="cloudrun-deployer"
RUNTIME_SA_NAME="cloudrun-runtime"
POOL_NAME="github-pool"
PROVIDER_NAME="github-provider"

# Crear Service Account para deploy (GitHub Actions)
if ! gcloud iam service-accounts describe "${SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com" &>/dev/null; then
    gcloud iam service-accounts create "$SA_NAME" --display-name="GitHub Actions Deployer"
fi

# Crear Service Account para runtime (Cloud Run)
if ! gcloud iam service-accounts describe "${RUNTIME_SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com" &>/dev/null; then
    gcloud iam service-accounts create "$RUNTIME_SA_NAME" --display-name="Cloud Run Runtime"
fi

# Asignar roles al deployer
SA_EMAIL="${SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"
ROLES=("roles/run.admin" "roles/artifactregistry.writer" "roles/iam.serviceAccountUser")

for ROLE in "${ROLES[@]}"; do
    gcloud projects add-iam-policy-binding "$PROJECT_ID" \
        --member="serviceAccount:$SA_EMAIL" \
        --role="$ROLE" \
        --condition=None --quiet >/dev/null
done

# Asignar roles al runtime SA (acceso a secretos)
RUNTIME_SA_EMAIL="${RUNTIME_SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
    --member="serviceAccount:$RUNTIME_SA_EMAIL" \
    --role="roles/secretmanager.secretAccessor" \
    --condition=None --quiet >/dev/null

# Crear Pool y Provider
if ! gcloud iam workload-identity-pools describe "$POOL_NAME" --location="global" &>/dev/null; then
    gcloud iam workload-identity-pools create "$POOL_NAME" --location="global" --display-name="GitHub Actions"
fi

if ! gcloud iam workload-identity-pools providers describe "$PROVIDER_NAME" --workload-identity-pool="$POOL_NAME" --location="global" &>/dev/null; then
    gcloud iam workload-identity-pools providers create-oidc "$PROVIDER_NAME" \
        --location="global" \
        --workload-identity-pool="$POOL_NAME" \
        --issuer-uri="https://token.actions.githubusercontent.com" \
        --attribute-mapping="google.subject=assertion.sub,attribute.actor=assertion.actor,attribute.repository=assertion.repository" \
        --attribute-condition="assertion.repository_owner == '${GITHUB_ORG}'"
fi

# Vincular Repo con Service Account
POOL_ID=$(gcloud iam workload-identity-pools describe "$POOL_NAME" --location="global" --format="value(name)")
gcloud iam service-accounts add-iam-policy-binding "$SA_EMAIL" \
    --role="roles/iam.workloadIdentityUser" \
    --member="principalSet://iam.googleapis.com/${POOL_ID}/attribute.repository/${GITHUB_ORG}/${GITHUB_REPO}" --quiet >/dev/null

PROVIDER_FULL_NAME=$(gcloud iam workload-identity-pools providers describe "$PROVIDER_NAME" --workload-identity-pool="$POOL_NAME" --location="global" --format="value(name)")

# ==============================================================================
# RESUMEN FINAL
# ==============================================================================
echo -e "\n${GREEN}✅ ¡CONFIGURACIÓN COMPLETADA CON ÉXITO!${NC}"
echo "------------------------------------------------------------------------"
echo "Guarda estos valores en GitHub (Settings > Secrets and variables > Actions):"
echo "------------------------------------------------------------------------"
echo -e "GCP_PROJECT_ID:                 ${GREEN}$PROJECT_ID${NC}"
echo -e "GCP_REGION:                     ${GREEN}$REGION${NC}"
echo -e "GCP_SERVICE_ACCOUNT:            ${GREEN}$SA_EMAIL${NC}"
echo -e "GCP_WORKLOAD_IDENTITY_PROVIDER: ${GREEN}$PROVIDER_FULL_NAME${NC}"
echo "------------------------------------------------------------------------"
echo ""
echo "Cloud Run runtime service account:"
echo -e "  ${GREEN}$RUNTIME_SA_EMAIL${NC}"
echo "------------------------------------------------------------------------"
