# Documentación Técnica - Lambdas de AWS

Documentación completa de las funciones Lambda utilizadas en el sistema de Customer Service Chat.

## 📋 Tabla de Contenidos

- [Descripción General](#-descripción-general)
- [1. HubSpot Ops Lambda](#1-hubspot-ops-lambda)
- [2. Interaction Ops Lambda](#2-interaction-ops-lambda)
- [3. Metrics Lambda](#3-metrics-lambda)
- [4. KB Ingest Lambda](#4-kb-ingest-lambda)
- [5. Post Confirmation Lambda](#5-post-confirmation-lambda)
- [6. Pre Signup Lambda](#6-pre-signup-lambda)
- [Consideraciones Generales](#-consideraciones-generales)

---

## 🎯 Descripción General

El sistema utiliza 6 funciones Lambda de AWS que se integran con Amazon Bedrock Agent para proporcionar capacidades avanzadas de:

- **Integración con HubSpot CRM** - Búsqueda y consulta de tickets, contactos y asociaciones
- **Gestión de Interacciones** - Transcripciones de llamadas y hilos de correo
- **Analytics y Métricas** - Consulta de métricas desde el backend FastAPI
- **Ingesta de Knowledge Base** - Sincronización de datos con Bedrock Knowledge Base
- **Gestión de Usuarios** - Triggers de Cognito para asignación de roles y validación

---

## 1. HubSpot Ops Lambda

### 📝 Descripción

Lambda que actúa como router OpenAPI para operaciones con HubSpot CRM. Proporciona endpoints para búsqueda y consulta de tickets, contactos, owners y asociaciones entre objetos.


### 🏗️ Arquitectura

- **Tipo**: Router basado en `apiPath` y `httpMethod`
- **Protocolo**: OpenAPI/Bedrock Agents
- **Versión de respuesta**: 1.0
- **Action Group**: `HubSpotOps`

### 🔗 Endpoints Soportados

#### 1.1. Tickets

##### `GET /tickets/{ticketId}`

Obtiene un ticket específico por su ID.

**Parámetros:**
- `ticketId` (path): ID del ticket en HubSpot

**Respuesta:**
```json
{
  "id": "string",
  "subject": "string",
  "createdate": "string",
  "closed_date": "string",
  "source_type": "string",
  "properties": { ... }
}
```

##### `GET /tickets/search`

Búsqueda avanzada de tickets con paginación y filtros.

**Parámetros de consulta:**
- `q` (string, opcional): Búsqueda de texto libre
- `page_size` (int, default: 5, max: 5): Tamaño de página
- `cursor` (string, opcional): Token de paginación
- `direction` (string, default: "next"): Dirección de paginación ("next" | "prev")
- `filters` (JSON string, opcional): Filtros avanzados
- `sort` (string, default: "createdate:DESC"): Ordenamiento
- `requested_total` (int, opcional): Total de resultados solicitados

**Características:**
- ✅ Detección automática de límite desde `inputText` usando patrones regex
- ✅ Paginación bidireccional con cursores
- ✅ Unificación de parámetros mediante `unify_ticket_params()`
- ✅ Soporte para filtros complejos (pipeline, stage, owner, priority, source, fechas)

**Respuesta:**
```json
{
  "tickets": [...],
  "count": 0,
  "page_size": 5,
  "has_more": false,
  "cursor_next": "string",
  "cursor_prev": "string",
  "remaining": 0,
  "requested_total": 5,
  "debug_info": { ... }
}
```

#### 1.2. Contactos

##### `GET /contacts/{contactId}`

Obtiene un contacto específico por su ID.

**Parámetros:**
- `contactId` (path): ID del contacto en HubSpot

**Respuesta:**
```json
{
  "id": "string",
  "firstname": "string",
  "lastname": "string",
  "name": "string",
  "email": "string",
  "phone": "string",
  "mobilephone": "string",
  "created_at": "string"
}
```

##### `GET /contacts/search`

Búsqueda de contactos con paginación.

**Parámetros de consulta:**
- `q` (string, opcional): Búsqueda por nombre, email o teléfono
- `page_size` (int, default: 5, max: 5): Tamaño de página
- `cursor` (string, opcional): Token de paginación
- `direction` (string, default: "next"): Dirección de paginación
- `filters` (JSON string, opcional): Filtros adicionales
- `sort` (string, default: "createdate:DESC"): Ordenamiento

**Respuesta:**
```json
{
  "contacts": [...],
  "count": 0,
  "page_size": 5,
  "has_more": false,
  "cursor_next": "string",
  "cursor_prev": "string",
  "remaining": 0
}
```

#### 1.3. Owners

##### `GET /owners/find`

Busca owners (propietarios) en HubSpot.

**Parámetros de consulta:**
- `ownerId` (string, opcional): ID específico del owner
- `q` (string, opcional): Búsqueda por nombre o email
- `page_size` (int, default: 5, max: 50): Tamaño de página

**Respuesta:**
```json
{
  "owners": [...],
  "page_size": 5,
  "has_more": false,
  "cursor_next": null,
  "cursor_prev": null,
  "remaining": 0
}
```

#### 1.4. Asociaciones

##### `GET /tickets/by-contact`

Obtiene todos los tickets asociados a un contacto.

**Parámetros de consulta:**
- `contactId` (string, requerido): ID del contacto
- `page_size` (int, default: 5, max: 100): Tamaño de página
- `cursor` (string, opcional): Token de paginación
- `direction` (string, default: "next"): Dirección de paginación
- `filters` (JSON string, opcional): Filtros adicionales
- `sort` (string, default: "createdate:DESC"): Ordenamiento

**Respuesta:**
```json
{
  "contactId": "string",
  "tickets": [...],
  "count": 0,
  "page_size": 5,
  "has_more": false,
  "cursor_next": "string",
  "cursor_prev": "string",
  "remaining": 0
}
```

##### `GET /tickets/{ticketId}/contacts`

Obtiene los contactos asociados a un ticket.

**Parámetros:**
- `ticketId` (path): ID del ticket

**Parámetros de consulta:**
- `primaryOnly` (boolean, default: false): Si es true, solo retorna el contacto principal
- `page_size` (int, default: 5, max: 100): Tamaño de página
- `cursor` (string, opcional): Token de paginación
- `direction` (string, default: "next"): Dirección de paginación

**Respuesta (múltiples contactos):**
```json
{
  "ticketId": "string",
  "contacts": [...],
  "page_size": 5,
  "has_more": false,
  "cursor_next": "string",
  "cursor_prev": "string",
  "remaining": 0
}
```

**Respuesta (contacto principal):**
```json
{
  "ticketId": "string",
  "primary_contact": { ... },
  "page_size": 1,
  "has_more": false,
  "cursor_next": null,
  "cursor_prev": null,
  "remaining": 0
}
```

### ⚙️ Variables de Entorno

| Variable | Descripción | Default |
|----------|-------------|---------|
| `HUBSPOT_TOKEN` | Token de autenticación de HubSpot | *Requerido* |
| `HUBSPOT_BASE_URL` | URL base de la API de HubSpot | `https://api.hubapi.com` |
| `HUBSPOT_TICKET_URL_BASE` | URL base para enlaces directos a tickets | - |
| `LOCAL_TZ` | Zona horaria local | `America/Costa_Rica` |
| `BUILD_TAG` | Tag para identificar deploys en logs | - |

### 📂 Archivos Principales

- `lambda_function.py` - Handler principal y router
- `tickets_helpers.py` - Lógica de búsqueda y unificación de tickets
- `contacts_helpers.py` - Lógica de búsqueda de contactos
- `associations_helpers.py` - Manejo de asociaciones entre objetos
- `owners_helpers.py` - Búsqueda y resolución de owners
- `config.py` - Configuración centralizada
- `date_utils.py` - Utilidades para manejo de fechas
- `utils.py` - Utilidades generales

### 🔧 Características Técnicas

- **Paginación**: Sistema de cursores base64 para navegación bidireccional
- **Detección de límites**: Extracción automática de límites desde texto natural usando regex
- **Caché**: Uso de `@lru_cache` para mapeos de stages y pipelines
- **Logging**: Sistema de logging estructurado con `BUILD_TAG` y `request_id`
- **Manejo de errores**: Captura de `HTTPError` de HubSpot con detalles
- **Validación**: Validación de parámetros y límites de paginación

### 📊 Límites y Restricciones

| Endpoint | `page_size` Máximo |
|----------|-------------------|
| Tickets | 5 |
| Contactos | 5 |
| Owners | 50 |
| Asociaciones | 100 |
| Filtros | Máximo 5 grupos, 18 filtros totales |

---

## 2. Interaction Ops Lambda

### 📝 Descripción

Lambda para obtener transcripciones de llamadas telefónicas y hilos de correo electrónico desde HubSpot. Soporta paginación y redacción de información sensible (PII).


### 🏗️ Arquitectura

- **Tipo**: Router minimalista basado en `apiPath`
- **Protocolo**: OpenAPI/Bedrock Agents
- **Versión**: 2.1.0
- **Action Group**: `InteractionOps`

### 🔗 Endpoints Soportados

#### 2.1. Transcripción de Llamadas

##### `GET /call-transcription/{ticketId}`

Obtiene la transcripción de una llamada telefónica asociada a un ticket.

**Parámetros:**
- `ticketId` (path): ID del ticket en HubSpot

**Parámetros de consulta:**
- `page_size` (int, default: 2000, max: 5000): Tamaño de página en caracteres
- `cursor` (string, opcional): Token de paginación
- `direction` (string, default: "next"): Dirección de paginación

**Flujo:**
1. Obtiene el ticket y valida que `source_type == "phone"`
2. Intenta leer la propiedad `hs_call_transcript`
3. Si no existe, intenta extraer desde `analisis_de_llamada` (legacy)
4. Aplica redacción de PII (tarjetas de crédito, DNI)
5. Pagina por caracteres según `page_size`

**Respuesta:**
```json
{
  "ticketId": "string",
  "transcription": "string",
  "has_more": false,
  "cursor_next": "string",
  "cursor_prev": "string"
}
```

**Errores:**
- `400`: Falta `ticketId`
- `404`: Ticket no encontrado o sin transcripción
- `422`: Ticket no corresponde a una llamada telefónica

#### 2.2. Hilo de Correos

##### `GET /email-thread/{ticketId}`

Obtiene el hilo completo de correos electrónicos asociados a un ticket.

**Parámetros:**
- `ticketId` (path): ID del ticket (opcional si se proporciona `threadId`)
- `threadId` (query, opcional): ID directo del thread de conversación

**Parámetros de consulta:**
- `page_size` (int, default: 5, max: 5): Cantidad de mensajes por página
- `cursor` (string, opcional): Token de paginación
- `direction` (string, default: "next"): Dirección de paginación

**Flujo:**
1. Si hay `threadId`, obtiene mensajes directamente
2. Si no, deriva `threadId` desde asociaciones del ticket
3. Normaliza mensajes de Conversations API a formato homogéneo
4. Filtra mensajes sin texto
5. Ordena cronológicamente (ascendente)
6. Pagina por cantidad de mensajes

**Respuesta:**
```json
{
  "ticketId": "string",
  "emails": [
    {
      "id": "string",
      "timestamp": "ISO8601",
      "direction": "string",
      "subject": "string",
      "text": "string"
    }
  ],
  "thread_order": "chronological_asc",
  "has_more": false,
  "cursor_next": "string",
  "cursor_prev": "string"
}
```

### ⚙️ Variables de Entorno

| Variable | Descripción | Default |
|----------|-------------|---------|
| `HUBSPOT_API_KEY` | API Key de HubSpot | *Requerido* |
| `HUBSPOT_API_BASE` | URL base de HubSpot API | `https://api.hubapi.com` |
| `ENFORCE_ALLOWED_ROLES` | Activar validación de roles | `true` |
| `ALLOWED_ROLES` | Roles permitidos separados por coma | `Agent,Supervisor` |
| `ECHO_SESSION_ATTRS` | Modo debug para mostrar atributos de sesión | `false` |

### 🔒 Seguridad y Control de Acceso

- **Validación de roles**: Por defecto solo permite `Agent` y `Supervisor`
- **Auditoría**: Registra en logs el rol, email e ID del usuario que invoca
- **Redacción PII**: Enmascara tarjetas de crédito (13-19 dígitos) y DNI (8 dígitos)

### 🔧 Características Técnicas

- **Paginación por caracteres**: Para transcripciones (cursor con `t`, `s`, `e`, `v`)
- **Paginación por mensajes**: Para hilos de email (cursor con índices)
- **Limpieza HTML**: Extracción y limpieza de contenido HTML en emails
- **Normalización de texto**: Eliminación de firmas y encabezados de respuesta
- **Fallback legacy**: Soporte para formato antiguo de transcripciones

### 📊 Límites

| Endpoint | `page_size` Máximo |
|----------|-------------------|
| Transcripciones | 5000 caracteres |
| Emails | 5 mensajes |
| Mensajes por thread | 200 (configurable via `MAX_CONVO_MSGS`) |

---

## 3. Metrics Lambda

### 📝 Descripción

Lambda que actúa como proxy para obtener métricas y analytics desde un backend FastAPI. Soporta múltiples endpoints de métricas con resolución de rangos de fechas en español.


### 🏗️ Arquitectura

- **Tipo**: Proxy/Adapter para backend FastAPI
- **Protocolo**: OpenAPI/Bedrock Agents y Function Schema
- **Action Group**: `Analytics`

### 🔗 Endpoints Soportados

#### 3.1. Top Categorías

##### `GET /analytics/categories`

Obtiene las categorías más frecuentes de tickets resueltos.

**Parámetros:**
- `from` (string, opcional): Fecha inicio (ISO o DD-MM-YYYY)
- `to` (string, opcional): Fecha fin (ISO o DD-MM-YYYY)
- `top` (int, default: 5, max: 25): Cantidad de categorías a retornar
- `range` / `when` / `dateRange` (string, opcional): Rango en español natural

**Respuesta:**
```json
{
  "success": true,
  "metric_id": "metrics.top_categories",
  "data": [...],
  "chart": { ... },
  "source": "rds:postgres:tickets.public.resolved_tickets"
}
```

#### 3.2. Top Subcategorías

##### `GET /analytics/subcategories`

Obtiene las subcategorías más frecuentes.

**Parámetros:** Igual que categorías

**Respuesta:**
```json
{
  "success": true,
  "metric_id": "metrics.top_subcategories",
  "data": [...],
  "chart": { ... }
}
```

#### 3.3. Tickets por Fuente

##### `GET /analytics/sources`

Distribución de tickets por fuente (EMAIL, PHONE, CHAT, FORM).

**Parámetros:** `from`, `to`, `range` / `when` / `dateRange`

**Respuesta:**
```json
{
  "success": true,
  "metric_id": "metrics.by_source",
  "data": [...],
  "chart": { ... }
}
```

#### 3.4. Top Agentes

##### `GET /analytics/agents`

Agentes con más tickets resueltos.

**Parámetros:**
- `from`, `to`, `top` (default: 5, max: 25): Fechas y cantidad

**Respuesta:**
```json
{
  "success": true,
  "metric_id": "metrics.top_agents",
  "data": [...],
  "chart": { ... }
}
```

#### 3.5. Volumen Cerrado

##### `GET /analytics/closed_volume`

Volumen total de tickets cerrados en el período.

**Parámetros:** `from`, `to`

**Respuesta:**
```json
{
  "success": true,
  "metric_id": "metrics.closed_volume",
  "data": [...],
  "chart": { ... }
}
```

#### 3.6. Tiempo de Resolución por Agente (Business)

##### `GET /analytics/resolution_time/by_agent_business`

Tiempo promedio de resolución por agente (horas de negocio).

**Parámetros:**
- `from`, `to`: Fechas
- `top` (default: 50): Cantidad de agentes

**Respuesta:**
```json
{
  "success": true,
  "metric_id": "metrics.resolution_time.by_agent_business",
  "data": [...],
  "chart": { ... }
}
```

#### 3.7. Tiempo Promedio de Resolución (Business)

##### `GET /analytics/resolution_time/avg_business`

Tiempo promedio general de resolución (horas de negocio).

**Parámetros:** `from`, `to`

**Respuesta:**
```json
{
  "success": true,
  "metric_id": "metrics.resolution_time.avg_business",
  "data": [...],
  "chart": { ... }
}
```

#### 3.8. Tiempo de Resolución por Fuente (Business)

##### `GET /analytics/resolution_time/by_source_business`

Tiempo promedio de resolución agrupado por fuente.

**Parámetros:**
- `from`, `to`: Fechas
- `order` (default: "asc"): Ordenamiento ("asc" | "desc")

**Respuesta:**
```json
{
  "success": true,
  "metric_id": "metrics.resolution_time.by_source_business",
  "data": [...],
  "chart": { ... }
}
```

#### 3.9. Casos Lentos (Business)

##### `GET /analytics/resolution_time/slow_cases_business`

Tickets con mayor tiempo de resolución (horas de negocio).

**Parámetros:**
- `from`, `to`: Fechas
- `top` (opcional, default: 10, max: 25): Cantidad de casos

**Respuesta:**
```json
{
  "success": true,
  "metric_id": "metrics.resolution_time.slow_cases_business",
  "data": [...],
  "chart": { ... }
}
```

### 📅 Resolución de Fechas en Español

La lambda soporta rangos de fechas en español natural:

- **Fechas específicas**: "2025-01-15", "15-01-2025"
- **Relativas**: "hoy", "ayer"
- **Semanas**: "esta semana", "semana pasada"
- **Meses**: "este mes", "mes pasado", "enero", "febrero 2024"
- **Rangos**: "últimos 7 días", "hace 3 días"
- **Rangos explícitos**: "entre 2025-01-01 y 2025-01-31"

### ⚙️ Variables de Entorno

| Variable | Descripción | Default |
|----------|-------------|---------|
| `FAST_API_BASE_URL` | URL base del backend FastAPI | *Requerido* |
| `INGEST_API_KEY` | API Key para autenticación con el backend | *Requerido* |
| `DEFAULT_TZ` | Zona horaria por defecto | `America/Costa_Rica` |
| `ENFORCE_SUPERVISOR_ONLY` | Restringir acceso solo a Supervisores | `true` |
| `INCLUDE_SOURCE` | Incluir campo `source` en respuestas | `false` |
| `STRINGIFY_BODY` | Serializar body como string JSON | `false` |
| `ECHO_SESSION_ATTRS` | Modo debug para atributos de sesión | `false` |
| `TOP_HARD_LIMIT` | Límite máximo para parámetro `top` | `25` |

### 🔒 Seguridad y Control de Acceso

- **Validación de roles**: Por defecto solo permite `Supervisor`
- **Propagación de contexto**: Envía headers `X-Acting-Role` y `X-Acting-User` al backend
- **Timeout**: 20 segundos para requests al backend

### 🔧 Características Técnicas

- **Dual mode**: Soporta OpenAPI y Function Schema
- **Resolución inteligente de fechas**: Combina parámetros explícitos con texto natural
- **Normalización de `top`**: Fuerza valores entre 1 y `TOP_HARD_LIMIT`
- **Manejo de errores**: Propaga errores del backend con códigos específicos

---

## 4. KB Ingest Lambda

### 📝 Descripción

Lambda que descarga tickets resueltos desde un backend API, los sube a S3 y dispara un job de ingesta en Amazon Bedrock Knowledge Base.


### 🏗️ Arquitectura

- **Tipo**: ETL Pipeline (Extract, Transform, Load)
- **Trigger**: Manual o programado (EventBridge)
- **Dependencias**: S3, Bedrock Agent

### 🔄 Flujo de Ejecución

1. **Lectura de Estado (Watermark)**
   - Lee `last_since` desde S3 (`S3_STATE_KEY`)
   - Si no existe, usa `DAYS_BACK_DEFAULT` días atrás desde ahora

2. **Descarga de Datos**
   - Construye URL: `{API_URL}?since={since}&limit={limit}`
   - Descarga NDJSON desde el backend
   - Valida respuesta (status 200)

3. **Procesamiento**
   - Calcula `max_closed_at` desde los registros descargados
   - Genera timestamp para nombre de archivo

4. **Upload a S3**
   - Sube archivo: `{DATA_PREFIX}resolved_tickets_{timestamp}.jsonl`
   - Content-Type: `application/x-ndjson`

5. **Inicia Ingesta KB**
   - Llama a `bedrock.start_ingestion_job()`
   - Pasa `knowledgeBaseId` y `dataSourceId`

6. **Actualización de Watermark** (si no es modo manual)
   - Actualiza `last_since` en S3 con `max_closed_at`

### 📥 Parámetros de Entrada (Event)

```json
{
  "since": "2025-01-15T00:00:00Z",  // Opcional: override de fecha
  "limit": 5000,                     // Opcional: override de límite
  "manual": true                     // Opcional: si true, no actualiza watermark
}
```

### 📤 Respuesta

```json
{
  "ok": true,
  "uploaded_key": "tickets/resolved_tickets_20250115_143022.jsonl",
  "ingestion_job_id": "string",
  "since_used": "2025-01-15T00:00:00Z",
  "limit_used": 5000,
  "manual": false,
  "new_since": "2025-01-20T10:30:00Z",  // Solo si no es manual
  "state_updated": true
}
```

### ⚙️ Variables de Entorno

| Variable | Descripción | Default |
|----------|-------------|---------|
| `API_URL` | URL del endpoint de exportación | *Requerido* |
| `API_KEY` | API Key para autenticación | Opcional |
| `DAYS_BACK_DEFAULT` | Días hacia atrás si no hay watermark | `2` |
| `S3_BUCKET` | Nombre del bucket S3 | *Requerido* |
| `S3_DATA_PREFIX` | Prefijo para archivos de datos | `tickets/` |
| `S3_STATE_KEY` | Ruta del archivo de estado | `tickets/_state/last_since.txt` |
| `KB_ID` | ID de la Knowledge Base en Bedrock | *Requerido* |
| `KB_DATASOURCE_ID` | ID del Data Source en Bedrock | *Requerido* |
| `AWS_REGION` | Región de AWS | `us-east-1` |

### 🔧 Características Técnicas

- **Watermarking**: Sistema de estado persistente en S3 para evitar duplicados
- **Formato NDJSON**: Cada línea es un JSON independiente
- **Modo manual**: Permite ejecuciones de prueba sin afectar el watermark
- **Timeout**: 60 segundos para descarga del backend
- **Manejo de errores**: Retorna códigos de error específicos por etapa

### 📊 Casos de Uso

- **Ejecución programada**: EventBridge trigger diario/semanal
- **Ejecución manual**: Para backfill o pruebas
- **Incremental**: Solo descarga tickets nuevos desde el último watermark

---

## 5. Post Confirmation Lambda

### 📝 Descripción

Lambda trigger de Cognito que se ejecuta después de la confirmación de usuario. Asigna automáticamente al usuario a un grupo (Agent o Supervisor) basado en su rol obtenido desde un servicio externo.


### 🏗️ Arquitectura

- **Tipo**: Cognito Post Confirmation Trigger
- **Trigger**: Automático después de `ConfirmSignUp` o `ConfirmForgotPassword`

### 🔄 Flujo de Ejecución

1. **Extracción de Datos**
   - Obtiene `email` desde `userAttributes`
   - Obtiene `username` desde el evento (importante para usuarios federados)

2. **Resolución de Rol**
   - Llama a `{ROLE_RESOLVER_URL}?email={email}`
   - Envía header `x-api-key: {ROLE_RESOLVER_API_KEY}`
   - Espera respuesta: `{"role": "Agent" | "Supervisor"}`

3. **Asignación de Grupo**
   - Llama a `cognito.admin_add_user_to_group()`
   - Asigna al grupo correspondiente al rol
   - Si falla la resolución, asigna "Agent" por defecto

### 📥 Evento de Entrada (Cognito)

```json
{
  "request": {
    "userAttributes": {
      "email": "user@example.com",
      ...
    }
  },
  "userName": "user@example.com"
}
```

### 📤 Respuesta

Retorna el mismo evento sin modificaciones (requerido por Cognito).

### ⚙️ Variables de Entorno

| Variable | Descripción | Default |
|----------|-------------|---------|
| `USER_POOL_ID` | ID del User Pool de Cognito | *Requerido* |
| `ROLE_RESOLVER_URL` | URL del servicio que resuelve roles por email | *Requerido* |
| `ROLE_RESOLVER_API_KEY` | API Key para autenticación con el servicio | *Requerido* |

### 🔧 Características Técnicas

- **Timeout**: 5 segundos para llamada al servicio de roles
- **Fallback**: Si falla la resolución, asigna "Agent" por defecto
- **Logging**: Registra errores en CloudWatch Logs
- **Federated users**: Soporta usuarios federados (username puede diferir de email)

### 🔒 Seguridad

- **API Key**: Autenticación con servicio externo
- **Permisos IAM**: Requiere `cognito-idp:AdminAddUserToGroup` en el User Pool

---

## 6. Pre Signup Lambda

### 📝 Descripción

Lambda trigger de Cognito que se ejecuta antes del registro de usuario. Valida que el email esté en una allowlist y auto-confirma/verifica el email si está permitido.


### 🏗️ Arquitectura

- **Tipo**: Cognito Pre Signup Trigger
- **Trigger**: Automático antes de `SignUp`

### 🔄 Flujo de Ejecución

1. **Extracción de Email**
   - Obtiene `email` desde `userAttributes` y lo normaliza a lowercase

2. **Validación en Allowlist**
   - Llama a `{ALLOWLIST_URL}?email={email}`
   - Envía header `x-api-key: {API_KEY}`
   - Espera respuesta: `{"allowed": true | false, "role": "..."}`

3. **Decisión**
   - Si `allowed == false` o falla la llamada: **Lanza excepción** (bloquea registro)
   - Si `allowed == true`: **Auto-confirma y verifica email**

### 📥 Evento de Entrada (Cognito)

```json
{
  "request": {
    "userAttributes": {
      "email": "user@example.com",
      ...
    }
  },
  "response": {}
}
```

### 📤 Evento de Salida (si permitido)

```json
{
  "request": { ... },
  "response": {
    "autoConfirmUser": true,
    "autoVerifyEmail": true
  }
}
```

### ⚙️ Variables de Entorno

| Variable | Descripción | Default |
|----------|-------------|---------|
| `ALLOWLIST_URL` | URL del servicio de allowlist | *Requerido* |
| `ALLOWLIST_API_KEY` | API Key para autenticación | *Requerido* |

### 🔧 Características Técnicas

- **Fail-secure**: Ante cualquier fallo, bloquea el registro
- **Timeout**: 5 segundos para llamada al servicio
- **Logging**: Registra errores en CloudWatch Logs
- **Auto-verificación**: Elimina necesidad de verificación manual de email

### 🔒 Seguridad

- **API Key**: Autenticación con servicio de allowlist
- **Política de seguridad**: Bloquea por defecto si no hay respuesta positiva explícita
- **Normalización**: Email siempre en lowercase para consistencia

### 📊 Casos de Uso

- **Control de acceso**: Solo usuarios invitados pueden registrarse
- **Onboarding controlado**: Integración con sistema de invitaciones
- **Auto-verificación**: Simplifica flujo de registro para usuarios permitidos

---

## 🔍 Consideraciones Generales

### 📝 Logging y Monitoreo

- Todas las lambdas implementan logging estructurado
- Uso de `print()` para CloudWatch Logs
- Inclusión de `request_id` y `BUILD_TAG` cuando aplica

### ⚠️ Manejo de Errores

- Captura de excepciones con mensajes descriptivos
- Códigos HTTP apropiados (400, 403, 404, 422, 500, 502)
- Propagación de errores de servicios upstream

### 🔒 Seguridad

- Validación de roles en lambdas sensibles (Metrics, Interaction Ops)
- API Keys para servicios externos
- Redacción de PII en transcripciones
- Fail-secure en validaciones críticas

### ⚡ Performance

- Uso de caché (`@lru_cache`) donde aplica
- Timeouts configurables
- Paginación para grandes volúmenes de datos
- Límites de tamaño de página para evitar timeouts

### 🔗 Integraciones

- **HubSpot**: API v3 y v4
- **Amazon Bedrock**: Knowledge Base y Agents
- **Amazon Cognito**: User Pools y Triggers
- **Amazon S3**: Almacenamiento de datos y estado
- **FastAPI Backend**: Métricas y analytics

---

## 📌 Versiones y Tags

| Lambda | Versión/Tag |
|--------|-------------|
| HubSpot Ops | `hubspotops-lambda-2025-10-31-debug1` (configurable via `BUILD_TAG`) |
| Interaction Ops | `2.1.0` |
| Metrics | Versión implícita en código |
| KB Ingest | Sin versión explícita |
| Post Confirmation | Versión robusta |
| Pre Signup | Versión segura |

---

## 📞 Soporte

Para soporte técnico o preguntas sobre las Lambdas, contacta al equipo de desarrollo o consulta los logs en CloudWatch.

---

**Última actualización:** 2024

