#!/bin/bash

# Nombre del directorio raíz
ROOT="oasis-api"
#mkdir -p $ROOT
#cd $ROOT

# 1. Crear carpeta común para lógica compartida (Base de Datos, Auth, Schemas)
mkdir -p common/auth common/database common/schemas
touch common/__init__.py
touch common/auth/__init__.py
touch common/database/__init__.py
touch common/schemas/__init__.py

# Archivos base de lógica compartida
touch common/auth/security.py
touch common/database/client.py
touch common/schemas/base.py

# 2. Definir los microservicios del ecosistema Oasis
SERVICES=("journey-service" "auth-service")

# 3. Crear estructura para cada servicio con centralizador api/v1
for SERVICE in "${SERVICES[@]}"


do
    #Convertir los guiones a guiones bajos para que los archivos sean considerados como paquetes de python
    PKG_NAME=$(echo "$SERVICE" | tr "-" "_")

    # Crear rutas de directorios: API (con v1 y endpoints), Core, y Tests
    BASE_PATH="services/$PKG_NAME"
    mkdir -p $BASE_PATH/api/v1/endpoints
    mkdir -p $BASE_PATH/core
    mkdir -p $BASE_PATH/tests
    mkdir -p $BASE_PATH/schemas
    mkdir -p $BASE_PATH/crud

    # Crear archivos __init__.py para que Python los reconozca como paquetes
    touch $BASE_PATH/__init__.py
    touch $BASE_PATH/api/__init__.py
    touch $BASE_PATH/api/v1/__init__.py
    touch $BASE_PATH/api/v1/endpoints/__init__.py
    touch $BASE_PATH/core/__init__.py
    touch $BASE_PATH/tests/__init__.py
    touch $BASE_PATH/schemas/__init__.py
    touch $BASE_PATH/crud/__init__.py

    # Archivos fundamentales del microservicio
    touch $BASE_PATH/main.py            # Punto de entrada FastAPI
    touch $BASE_PATH/api/v1/api.py      # CENTRALIZADOR de rutas v1
    touch $BASE_PATH/core/config.py     # Configuración Pydantic


    echo "🏗️  Servicio creado: $BASE_PATH"
done

# --- 3. El Orquestador (LA CLAVE PARA TU Oasis API v 0.1.0) ---
# Este archivo unificará todo en una sola URL
touch main.py

# 4. Crear carpeta de recursos estáticos (ej: logo para el README)
mkdir -p public

# 5. Archivos raíz del proyecto
#touch docker-compose.yml
touch .env.example
touch .gitignore
touch pyproject.toml
touch README.md
touch .pre-commit-config.yaml

echo "✅ Estructura lista. Usar $ROOT/main.py para desplegar la version 0.1.0"
