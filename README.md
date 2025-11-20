# Customer Service Chat - Backend API

Backend FastAPI completo para el sistema de chat de servicio al cliente con integración de Amazon Bedrock Agent, autenticación con AWS Cognito, y gestión de base de datos PostgreSQL.

## 📋 Tabla de Contenidos

- [Descripción](#-descripción)
- [Características Principales](#-características-principales)
- [Arquitectura](#-arquitectura)
- [Tecnologías](#-tecnologías)
- [Estructura del Proyecto](#-estructura-del-proyecto)
- [Requisitos Previos](#-requisitos-previos)
- [Instalación](#-instalación)
- [Configuración](#-configuración)
- [Variables de Entorno](#-variables-de-entorno)
- [Ejecución](#-ejecución)
- [Documentación de la API](#-documentación-de-la-api)
- [Endpoints Principales](#-endpoints-principales)
- [Autenticación](#-autenticación)
- [Base de Datos](#-base-de-datos)
- [Despliegue](#-despliegue)
- [Docker](#-docker)
- [Troubleshooting](#-troubleshooting)
- [Contribución](#-contribución)

## 🎯 Descripción

Este backend proporciona una API REST completa para un sistema de chat de servicio al cliente que utiliza Amazon Bedrock Agent para generar respuestas inteligentes. El sistema incluye:

- **Chat en tiempo real** con Amazon Bedrock Agent
- **Autenticación y autorización** con AWS Cognito
- **Gestión de usuarios** con roles (Agent, Supervisor)
- **Sistema de invitaciones** para nuevos usuarios
- **Gestión de base de datos** PostgreSQL para tickets y métricas
- **API de ingesta de datos** para cargar información histórica
- **Integración con HubSpot** para sincronización de datos

## ✨ Características Principales

### Chat y Bedrock Agent
- ✅ Integración completa con Amazon Bedrock Agent
- ✅ Gestión de sesiones de chat
- ✅ Trazabilidad de conversaciones (trace)
- ✅ Inyección de atributos de sesión (rol, email, grupos)
- ✅ Manejo de timeouts y reintentos
- ✅ Prueba de conexión con el agente

### Autenticación y Autorización
- ✅ OAuth 2.0 con AWS Cognito
- ✅ Autenticación basada en cookies HttpOnly
- ✅ Validación de tokens JWT
- ✅ Sistema de roles (Agent, Supervisor)
- ✅ Verificación de allowlist
- ✅ Gestión de estado de usuarios (active, pending, disabled)

### Gestión de Usuarios
- ✅ CRUD completo de usuarios
- ✅ Sistema de invitaciones por email
- ✅ Aceptación de invitaciones
- ✅ Asignación de roles administrativos
- ✅ Sincronización con Cognito

### Base de Datos
- ✅ Conexión a PostgreSQL (RDS)
- ✅ Health checks de base de datos
- ✅ Estadísticas y métricas
- ✅ API de ingesta de datos
- ✅ Consultas personalizadas

## 🏗️ Arquitectura

```
┌─────────────────┐
│   Frontend      │
│   (Next.js)     │
└────────┬────────┘
         │ HTTP/REST
         │
┌────────▼─────────────────────────────────────┐
│         FastAPI Backend                      │
│  ┌──────────────────────────────────────┐   │
│  │  Auth Layer (Cognito)                │   │
│  │  - OAuth 2.0                         │   │
│  │  - JWT Validation                    │   │
│  │  - Role-based Access                 │   │
│  └──────────────────────────────────────┘   │
│  ┌──────────────────────────────────────┐   │
│  │  Chat API                            │   │
│  │  - Bedrock Agent Integration         │   │
│  │  - Session Management                │   │
│  └──────────────────────────────────────┘   │
│  ┌──────────────────────────────────────┐   │
│  │  Data Management API                 │   │
│  │  - Ingest API                        │   │
│  │  - Database Queries                  │   │
│  └──────────────────────────────────────┘   │
│  ┌──────────────────────────────────────┐   │
│  │  User Management API                 │   │
│  │  - Invitations                       │   │
│  │  - User CRUD                         │   │
│  └──────────────────────────────────────┘   │
└────────┬─────────────────────────────────────┘
         │
    ┌────┴────┬──────────────┬──────────────┐
    │         │              │              │
┌───▼───┐ ┌──▼──────┐  ┌────▼─────┐  ┌────▼─────┐
│ AWS   │ │ AWS     │  │PostgreSQL│  │ HubSpot  │
│Bedrock│ │ Cognito │  │   RDS    │  │   API    │
│Agent  │ │         │  │          │  │          │
└───────┘ └─────────┘  └──────────┘  └──────────┘
```

## 🛠️ Tecnologías

- **FastAPI** 0.119.0 - Framework web moderno y rápido
- **Python** 3.11+ - Lenguaje de programación
- **Uvicorn** - Servidor ASGI de alto rendimiento
- **Boto3** - SDK de AWS para Python
- **PostgreSQL** - Base de datos relacional (psycopg2-binary)
- **Pydantic** - Validación de datos y modelos
- **Python-JOSE** - Manejo de tokens JWT
- **Python-dotenv** - Gestión de variables de entorno

## 📁 Estructura del Proyecto

```
customer-service-chat-backend/
├── main.py                      # Aplicación FastAPI principal
├── requirements.txt             # Dependencias Python
├── Dockerfile                   # Configuración Docker
├── README.md                    # Este archivo
├── GUIA_EJECUCION.md           # Guía detallada de ejecución
│
└── src/
    ├── auth/                    # Módulo de autenticación
    │   ├── cognito.py           # Cliente de Cognito
    │   ├── cognito_admin.py     # Operaciones admin de Cognito
    │   ├── deps.py              # Dependencias de autenticación
    │   ├── invite_api.py        # API de invitaciones
    │   ├── accept_api.py        # API de aceptación de invitaciones
    │   ├── users_api.py         # API de gestión de usuarios
    │   ├── admin_roles_api.py   # API de roles administrativos
    │   └── allowlist_check.py   # Verificación de allowlist
    │
    ├── services/                # Servicios de negocio
    │   ├── bedrock_service.py   # Servicio de Bedrock Agent
    │   └── role_sync_service.py # Sincronización de roles
    │
    ├── database/                # Módulo de base de datos
    │   ├── db_utils.py          # Utilidades de base de datos
    │   └── data_management_api.py # API de gestión de datos
    │
    └── config/                  # Configuración
        ├── settings.py          # Configuraciones de la aplicación
        └── secrets.py           # Gestión de secretos (AWS Secrets Manager)
```

## 📋 Requisitos Previos

- **Python** 3.11 o superior
- **PostgreSQL** 12+ (o acceso a RDS)
- **AWS Account** con:
  - Amazon Bedrock Agent configurado
  - AWS Cognito User Pool configurado
  - AWS Secrets Manager (opcional, para producción)
  - Permisos IAM apropiados
- **Node.js** (solo para desarrollo frontend)

## 🚀 Instalación

### 1. Clonar el Repositorio

```bash
git clone <repository-url>
cd customer-service-chat-backend
```

### 2. Crear Entorno Virtual

```bash
# Crear entorno virtual
python -m venv venv

# Activar entorno virtual
# En macOS/Linux:
source venv/bin/activate

# En Windows:
venv\Scripts\activate
```

### 3. Instalar Dependencias

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### 4. Verificar Instalación

```bash
python --version  # Debe ser 3.11+
pip list          # Verificar que las dependencias estén instaladas
```

## ⚙️ Configuración

### Variables de Entorno

El proyecto utiliza AWS Secrets Manager para producción y variables de entorno para desarrollo local.

#### Desarrollo Local

Crea un archivo `.env` en la raíz del proyecto:

```bash
# AWS Configuration
AWS_REGION=us-east-1
AWS_ACCESS_KEY_ID=your_access_key
AWS_SECRET_ACCESS_KEY=your_secret_key

# Bedrock Agent
BEDROCK_AGENT_ID=PJSUJU8ACS
BEDROCK_AGENT_ALIAS_ID=customer-service
BEDROCK_AGENT_ARN=arn:aws:bedrock:us-east-1:792655899277:agent/PJSUJU8ACS
BEDROCK_CONNECT_TIMEOUT=30
BEDROCK_READ_TIMEOUT=120
BEDROCK_MAX_RETRIES=3
BEDROCK_RETRY_DELAY=2.0

# PostgreSQL Database
DB_HOST=your-db-host.rds.amazonaws.com
DB_PORT=5432
DB_NAME=your_database_name
DB_USER=your_db_user
DB_PASSWORD=your_db_password

# AWS Cognito
COGNITO_REGION=us-east-1
COGNITO_USER_POOL_ID=us-east-1_XXXXXXXXX
COGNITO_CLIENT_ID=your_client_id
COGNITO_CLIENT_SECRET=your_client_secret
COGNITO_DOMAIN=your-domain.auth.us-east-1.amazoncognito.com
OAUTH_REDIRECT_URI=http://localhost:3000/login/callback

# Cookie Configuration
COOKIE_DOMAIN=localhost
COOKIE_SECURE=false
COOKIE_SAMESITE=lax

# CORS
CORS_ORIGINS=http://localhost:3000,http://localhost:3001
FRONTEND_URL=http://localhost:3000

# API Keys
INGEST_API_KEY=your_ingest_api_key
UI_HINT_SECRET=your_ui_hint_secret

# HubSpot (opcional)
HUBSPOT_TOKEN=your_hubspot_token
HUBSPOT_BASE_URL=https://api.hubapi.com

# AWS Secrets Manager (opcional, para producción)
AWS_SECRETS_MANAGER_SECRET_NAME=your-secret-name
```

#### Producción

En producción, las variables se obtienen de AWS Secrets Manager. Configura el secreto con todas las variables anteriores.

### Configuración de AWS

1. **Configurar credenciales AWS:**
   ```bash
   aws configure
   ```

2. **Verificar permisos IAM:**
   - `bedrock:InvokeAgent`
   - `cognito-idp:*` (para gestión de usuarios)
   - `secretsmanager:GetSecretValue` (si usas Secrets Manager)

3. **Configurar Bedrock Agent:**
   - Asegúrate de que el Agent ID y Alias ID sean correctos
   - Verifica que el Agent esté activo en la consola de AWS

### Configuración de Base de Datos

1. **Crear base de datos PostgreSQL:**
   ```sql
   CREATE DATABASE customer_service_chat;
   ```

2. **Crear tablas necesarias:**
   - Consulta `GUIA_EJECUCION.md` para el esquema completo
   - O ejecuta los scripts de migración si están disponibles

3. **Verificar conexión:**
   ```bash
   python -c "from src.database.db_utils import test_connection; print('OK' if test_connection() else 'FAIL')"
   ```

## 🏃 Ejecución

### Desarrollo

```bash
# Activar entorno virtual
source venv/bin/activate

# Ejecutar servidor de desarrollo con auto-reload
python main.py
```

El servidor estará disponible en: `http://localhost:8000`

### Producción

```bash
# Con Uvicorn directamente
uvicorn main:app --host 0.0.0.0 --port 8000 --workers 2 --access-log
```

### Con Docker

```bash
# Construir imagen
docker build -t customer-service-chat-backend .

# Ejecutar contenedor
docker run -p 8000:8000 --env-file .env customer-service-chat-backend
```

## 📚 Documentación de la API

Una vez que el servidor esté ejecutándose, puedes acceder a:

- **Swagger UI (Interactivo):** `http://localhost:8000/docs`
- **ReDoc (Documentación):** `http://localhost:8000/redoc`
- **OpenAPI JSON:** `http://localhost:8000/openapi.json`

## 🔗 Endpoints Principales

### Chat
#### `POST /api/chat`
Envía un mensaje al agente de Bedrock.

**Autenticación:** Requerida (cookie `id_token`)

**Request:**
```json
{
  "message": "¿Cuántos tickets se resolvieron esta semana?",
  "session_id": "optional-session-id"
}
```

**Response:**
```json
{
  "success": true,
  "response": "Esta semana se resolvieron 45 tickets...",
  "session_id": "abc123...",
  "trace": [...]
}
```

#### `GET /api/agent/info`
Obtiene información del agente de Bedrock configurado.

**Response:**
```json
{
  "agent_id": "PJSUJU8ACS",
  "agent_alias_id": "customer-service",
  "region": "us-east-1",
  "arn": "arn:aws:bedrock:us-east-1:792655899277:agent/PJSUJU8ACS"
}
```

#### `POST /api/agent/test-connection`
Prueba la conexión con el agente de Bedrock.

**Response:**
```json
{
  "success": true,
  "message": "Conexión exitosa",
  "agent_info": {...}
}
```

### Autenticación

#### `POST /auth/exchange`
Intercambia el código de autorización OAuth por tokens.

**Request:**
```
Content-Type: application/x-www-form-urlencoded
code=authorization_code
```

**Response:**
```json
{
  "ok": true,
  "email": "user@example.com"
}
```
*Establece cookie `id_token` HttpOnly*

#### `GET /auth/me`
Obtiene información del usuario autenticado.

**Autenticación:** Requerida

**Response:**
```json
{
  "email": "user@example.com",
  "groups": ["Agent"],
  "given_name": "John",
  "family_name": "Doe"
}
```

#### `POST /auth/logout`
Cierra la sesión del usuario.

**Response:**
```json
{
  "ok": true
}
```

### Gestión de Usuarios

#### `GET /api/users`
Lista todos los usuarios (requiere rol Supervisor).

#### `POST /api/users/invite`
Envía una invitación a un nuevo usuario.

#### `GET /api/users/{email}`
Obtiene información de un usuario específico.

#### `PUT /api/users/{email}`
Actualiza un usuario.

#### `DELETE /api/users/{email}`
Elimina un usuario.

### Base de Datos

#### `GET /api/database/health`
Verifica el estado de la base de datos.

**Response:**
```json
{
  "success": true,
  "message": "Base de datos conectada"
}
```

#### `GET /api/database/stats`
Obtiene estadísticas de la base de datos.

**Response:**
```json
{
  "success": true,
  "total_tickets": 1234,
  "categories": [
    {"category": "Technical", "count": 500},
    {"category": "Billing", "count": 400}
  ]
}
```

### Gestión de Datos

#### `POST /data/ingest`
Ingesta datos en la base de datos (requiere API key).

#### `GET /data/query`
Ejecuta consultas personalizadas en la base de datos.

## 🔐 Autenticación

### Flujo de Autenticación

1. **Usuario inicia sesión en el frontend**
   - Redirige a Cognito Hosted UI
   - Usuario se autentica

2. **Cognito redirige al callback**
   - Frontend recibe código de autorización
   - Frontend envía código a `/auth/exchange`

3. **Backend intercambia código por tokens**
   - Valida el código con Cognito
   - Obtiene tokens (id_token, access_token, refresh_token)
   - Establece cookie HttpOnly con `id_token`

4. **Requests subsecuentes**
   - Frontend envía cookie automáticamente
   - Backend valida token en cada request
   - Extrae información del usuario (email, grupos, roles)

### Roles y Permisos

- **Agent**: Acceso básico al chat
- **Supervisor**: Acceso completo, incluyendo gestión de usuarios y métricas

Los roles se determinan por los grupos de Cognito:
- Usuario en grupo "Supervisor" → Rol Supervisor
- Usuario sin grupo o en grupo "Agent" → Rol Agent

### Atributos de Sesión

El backend inyecta automáticamente atributos de sesión en cada invocación del agente:

```python
{
  "role": "Supervisor" | "Agent",
  "user_email": "user@example.com",
  "user_id": "cognito-user-id",
  "groups": "Supervisor,Agent"
}
```

Estos atributos están disponibles para:
- El orquestador de Bedrock (para decidir qué funciones invocar)
- Las Lambdas de Bedrock (para personalizar respuestas)

## 💾 Base de Datos

### Esquema Principal

El sistema utiliza PostgreSQL con las siguientes tablas principales:

- `resolved_tickets` - Tickets resueltos
- `users` - Usuarios del sistema
- `invitations` - Invitaciones pendientes

Consulta `GUIA_EJECUCION.md` para el esquema completo.

### Conexión

La conexión se gestiona mediante `db_utils.py`:

```python
from src.database.db_utils import execute_query, test_connection

# Probar conexión
if test_connection():
    print("Conexión exitosa")

# Ejecutar query
result = execute_query("SELECT * FROM resolved_tickets LIMIT 10")
```

## 🚢 Despliegue

### AWS Elastic Beanstalk

1. **Instalar EB CLI:**
   ```bash
   pip install awsebcli
   ```

2. **Inicializar aplicación:**
   ```bash
   eb init -p python-3.11 customer-service-chat-backend
   ```

3. **Crear entorno:**
   ```bash
   eb create production
   ```

4. **Configurar variables de entorno en la consola de AWS**

5. **Desplegar:**
   ```bash
   eb deploy
   ```

### AWS Lambda + API Gateway

1. **Empaquetar aplicación:**
   ```bash
   pip install -r requirements.txt -t .
   zip -r lambda-deployment.zip .
   ```

2. **Crear función Lambda**
3. **Configurar API Gateway**
4. **Configurar variables de entorno en Lambda**

### Docker en ECS/Fargate

1. **Construir y subir imagen:**
   ```bash
   docker build -t customer-service-chat-backend .
   docker tag customer-service-chat-backend:latest <account>.dkr.ecr.<region>.amazonaws.com/customer-service-chat-backend:latest
   docker push <account>.dkr.ecr.<region>.amazonaws.com/customer-service-chat-backend:latest
   ```

2. **Crear servicio ECS/Fargate**
3. **Configurar variables de entorno desde Secrets Manager**

## 🐳 Docker

### Dockerfile

El proyecto incluye un `Dockerfile` optimizado:

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Instalar dependencias del sistema
RUN apt-get update && apt-get install -y \
    gcc \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Copiar e instalar dependencias Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar código de la aplicación
COPY . .

# Exponer puerto
EXPOSE 8000

# Comando por defecto
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### Docker Compose (Desarrollo)

Crea un `docker-compose.yml`:

```yaml
version: '3.8'

services:
  backend:
    build: .
    ports:
      - "8000:8000"
    environment:
      - DB_HOST=db
      - DB_NAME=customer_service_chat
      - DB_USER=postgres
      - DB_PASSWORD=postgres
    depends_on:
      - db
    volumes:
      - .:/app

  db:
    image: postgres:15
    environment:
      - POSTGRES_DB=customer_service_chat
      - POSTGRES_USER=postgres
      - POSTGRES_PASSWORD=postgres
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data

volumes:
  postgres_data:
```

Ejecutar:
```bash
docker-compose up
```

## 🔧 Troubleshooting

### Error: "No module named 'src'"

**Solución:** Asegúrate de ejecutar desde la raíz del proyecto:
```bash
cd customer-service-chat-backend
python main.py
```

### Error: "Connection timeout" con Bedrock

**Solución:**
1. Verifica que las credenciales AWS estén configuradas
2. Verifica que el Agent ID sea correcto
3. Aumenta `BEDROCK_READ_TIMEOUT` si las respuestas son lentas

### Error: "Database connection failed"

**Solución:**
1. Verifica que PostgreSQL esté ejecutándose
2. Verifica las credenciales de base de datos
3. Verifica que el host sea accesible desde tu red
4. Prueba la conexión manualmente:
   ```bash
   psql -h <DB_HOST> -U <DB_USER> -d <DB_NAME>
   ```

### Error: "Cognito token validation failed"

**Solución:**
1. Verifica que `COGNITO_USER_POOL_ID` sea correcto
2. Verifica que `COGNITO_CLIENT_ID` sea correcto
3. Verifica que el token no haya expirado
4. Revisa los logs para más detalles

### Error: CORS

**Solución:**
1. Verifica que `CORS_ORIGINS` incluya el dominio del frontend
2. Verifica que `COOKIE_DOMAIN` esté configurado correctamente
3. En desarrollo, asegúrate de incluir `http://localhost:3000`

### Logs

Para ver logs detallados:

```bash
# Desarrollo
python main.py

# Producción con logs
uvicorn main:app --host 0.0.0.0 --port 8000 --log-level debug
```

