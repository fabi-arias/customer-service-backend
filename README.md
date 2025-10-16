# Customer Service Chat - Backend API

Backend FastAPI para el sistema de chat de servicio al cliente con Amazon Bedrock Agent.

## 🚀 Características

- **FastAPI** como framework web
- **Amazon Bedrock Agent** para respuestas inteligentes
- **PostgreSQL** para almacenamiento de datos
- **APIs RESTful** para el frontend
- **CORS configurado** para desarrollo frontend

## 📁 Estructura del Proyecto

```
customer-service-chat-backend/
├── main.py                 # Aplicación FastAPI principal
├── requirements.txt        # Dependencias Python
├── README.md              # Este archivo
└── src/
    ├── services/
    │   └── bedrock_service.py    # Servicio de Bedrock Agent
    ├── database/
    │   ├── db_utils.py           # Utilidades de base de datos
    │   └── ingest_api.py         # API de ingesta de datos
    └── config/
        └── settings.py           # Configuraciones
```

## 🛠️ Instalación

1. **Crear entorno virtual:**
```bash
python -m venv venv
source venv/bin/activate  # En Windows: venv\Scripts\activate
```

2. **Instalar dependencias:**
```bash
pip install -r requirements.txt
```

3. **Configurar variables de entorno:**
```bash
# Crear archivo .env con tus configuraciones
cp .env.example .env
# Editar .env con tus credenciales AWS y base de datos
```

## 🚀 Ejecución

### Desarrollo
```bash
python main.py
```

### Producción
```bash
uvicorn main:app --host 0.0.0.0 --port 8000
```

La API estará disponible en: `http://localhost:8000`

## 📚 Documentación de la API

Una vez ejecutando, puedes acceder a:
- **Swagger UI:** `http://localhost:8000/docs`
- **ReDoc:** `http://localhost:8000/redoc`

## 🔗 Endpoints Principales

### Chat
- `POST /api/chat` - Enviar mensaje al agente
- `GET /api/agent/info` - Información del agente
- `POST /api/agent/test-connection` - Probar conexión

### Base de Datos
- `GET /api/database/health` - Estado de la BD
- `GET /api/database/stats` - Estadísticas

### Sistema
- `GET /` - Información de la API
- `GET /health` - Health check

## 🔧 Configuración

El backend usa las mismas configuraciones que el proyecto original:
- **AWS Bedrock Agent** (configurado en `src/config/settings.py`)
- **PostgreSQL** (configurado en `src/config/settings.py`)

## 🐳 Docker (Opcional)

```dockerfile
FROM python:3.9-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .
EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

## 🔄 Migración desde Streamlit

Este backend mantiene **toda la lógica original**:
- ✅ `bedrock_service.py` - Sin cambios
- ✅ `db_utils.py` - Sin cambios  
- ✅ `ingest_api.py` - Sin cambios
- ✅ Configuraciones - Sin cambios

Solo se agregó **FastAPI como capa de API** para el frontend React.

