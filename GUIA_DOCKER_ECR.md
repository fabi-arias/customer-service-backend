# 🐳 Guía Completa: Docker y AWS ECR para Backend

## 📚 Tabla de Contenidos
1. [¿Qué es Docker?](#qué-es-docker)
2. [Instalación en Mac](#instalación-en-mac)
3. [Conceptos Básicos](#conceptos-básicos)
4. [Crear Dockerfile](#crear-dockerfile)
5. [Construir Imagen Docker](#construir-imagen-docker)
6. [Configurar AWS ECR](#configurar-aws-ecr)
7. [Subir Imagen a ECR](#subir-imagen-a-ecr)
8. [Comandos Útiles](#comandos-útiles)
9. [Troubleshooting](#troubleshooting)

---

## ¿Qué es Docker?

**Docker** es una plataforma de contenedorización que permite empaquetar una aplicación y todas sus dependencias en un contenedor ligero y portable.

### Ventajas:
- ✅ **Consistencia**: La aplicación funciona igual en cualquier entorno
- ✅ **Aislamiento**: Cada contenedor es independiente
- ✅ **Portabilidad**: Funciona en Mac, Linux, Windows, servidores
- ✅ **Escalabilidad**: Fácil de replicar y escalar
- ✅ **Versionado**: Cada imagen tiene una versión específica

### Conceptos Clave:
- **Imagen**: Plantilla de solo lectura (como una clase)
- **Contenedor**: Instancia ejecutable de una imagen (como un objeto)
- **Dockerfile**: Archivo de texto con instrucciones para construir una imagen
- **Registry**: Repositorio donde se almacenan imágenes (como Docker Hub, ECR)

---

## Instalación en Mac

### Opción 1: Docker Desktop (Recomendado)

1. **Descargar Docker Desktop:**
   ```bash
   # Visita: https://www.docker.com/products/docker-desktop/
   # O descarga directamente:
   open https://download.docker.com/mac/stable/Docker.dmg
   ```

2. **Instalar:**
   - Abre el archivo `.dmg` descargado
   - Arrastra Docker a la carpeta Applications
   - Abre Docker desde Applications
   - Acepta los términos y condiciones

3. **Verificar instalación:**
   ```bash
   docker --version
   docker-compose --version
   ```

### Opción 2: Homebrew

```bash
# Instalar Docker Desktop via Homebrew
brew install --cask docker

# Iniciar Docker Desktop
open /Applications/Docker.app
```

### Verificar que Docker está corriendo:

```bash
# Debe mostrar información del sistema Docker
docker info

# Debe mostrar "Hello from Docker!"
docker run hello-world
```

---

## Conceptos Básicos

### Comandos Esenciales:

```bash
# Ver imágenes locales
docker images

# Ver contenedores corriendo
docker ps

# Ver todos los contenedores (incluyendo detenidos)
docker ps -a

# Ejecutar un contenedor
docker run <imagen>

# Detener un contenedor
docker stop <container_id>

# Eliminar un contenedor
docker rm <container_id>

# Eliminar una imagen
docker rmi <imagen_id>

# Ver logs de un contenedor
docker logs <container_id>

# Entrar a un contenedor corriendo
docker exec -it <container_id> /bin/bash
```

---

## Crear Dockerfile

Un **Dockerfile** es un archivo de texto que contiene instrucciones para construir tu imagen Docker.

### Estructura del Dockerfile para tu Backend:

```dockerfile
# Usar imagen base de Python 3.11 slim (más ligera)
FROM python:3.11-slim

# Establecer directorio de trabajo
WORKDIR /app

# Instalar dependencias del sistema (necesarias para psycopg2)
RUN apt-get update && apt-get install -y \
    gcc \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Copiar archivo de dependencias
COPY requirements.txt .

# Instalar dependencias Python
RUN pip install --no-cache-dir -r requirements.txt

# Copiar código de la aplicación
COPY . .

# Exponer puerto 8000 (puerto de FastAPI)
EXPOSE 8000

# Variable de entorno para Python (evita buffering)
ENV PYTHONUNBUFFERED=1

# Comando para ejecutar la aplicación
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### Explicación línea por línea:

- `FROM python:3.11-slim`: Imagen base con Python 3.11 (versión ligera)
- `WORKDIR /app`: Establece `/app` como directorio de trabajo
- `RUN apt-get update...`: Instala dependencias del sistema necesarias para PostgreSQL
- `COPY requirements.txt .`: Copia el archivo de dependencias
- `RUN pip install...`: Instala las dependencias Python
- `COPY . .`: Copia todo el código al contenedor
- `EXPOSE 8000`: Documenta que la app usa el puerto 8000
- `ENV PYTHONUNBUFFERED=1`: Evita buffering de salida de Python
- `CMD [...]`: Comando que se ejecuta al iniciar el contenedor

### Crear archivo `.dockerignore`:

Para evitar copiar archivos innecesarios al contenedor:

```dockerignore
# Entorno virtual
venv/
__pycache__/
*.pyc
*.pyo
*.pyd

# Archivos de desarrollo
.env.local
.env.development
.git/
.gitignore

# Archivos del sistema
.DS_Store
*.swp
*.swo

# Logs
*.log

# Cache
cache/
*.cache

# Documentación
*.md
!README.md

# Tests
tests/
*.test.py
```

---

## Construir Imagen Docker

### 1. Navegar al directorio del proyecto:

```bash
cd /Users/fabianaariasrosales/Desktop/customer-service-chat-backend
```

### 2. Construir la imagen:

```bash
# Formato básico
docker build -t customer-service-chat-backend .

# Con tag específico (recomendado)
docker build -t customer-service-chat-backend:1.0.0 .

# Con tag latest también
docker build -t customer-service-chat-backend:1.0.0 -t customer-service-chat-backend:latest .
```

**Explicación:**
- `-t`: Tag (nombre) de la imagen
- `.`: Directorio actual (donde está el Dockerfile)

### 3. Verificar que la imagen se creó:

```bash
docker images | grep customer-service-chat-backend
```

### 4. Probar la imagen localmente:

```bash
# Ejecutar el contenedor
docker run -p 8000:8000 \
  -e AWS_ACCESS_KEY_ID=tu_access_key \
  -e AWS_SECRET_ACCESS_KEY=tu_secret_key \
  -e DATABASE_URL=tu_database_url \
  customer-service-chat-backend:1.0.0

# O con archivo .env (si lo tienes)
docker run -p 8000:8000 --env-file .env customer-service-chat-backend:1.0.0
```

**Explicación:**
- `-p 8000:8000`: Mapea puerto 8000 del contenedor al puerto 8000 del host
- `-e`: Define variables de entorno
- `--env-file`: Carga variables de entorno desde un archivo

### 5. Verificar que funciona:

```bash
# En otra terminal
curl http://localhost:8000/health
```

---

## Configurar AWS ECR

**Amazon ECR (Elastic Container Registry)** es el registro de contenedores de AWS, similar a Docker Hub pero privado y integrado con AWS.

### Prerrequisitos:

1. **AWS CLI instalado:**
   ```bash
   # Verificar si está instalado
   aws --version

   # Si no está instalado, instalar con Homebrew
   brew install awscli
   ```

2. **Configurar credenciales AWS:**
   ```bash
   # Configurar credenciales
   aws configure

   # Te pedirá:
   # - AWS Access Key ID
   # - AWS Secret Access Key
   # - Default region (ej: us-east-1)
   # - Default output format (json)
   ```

3. **Verificar configuración:**
   ```bash
   # Ver tu identidad actual
   aws sts get-caller-identity
   ```

### Crear Repositorio en ECR:

#### Opción 1: Desde AWS Console

1. Ve a **ECR** en AWS Console
2. Click en **"Create repository"**
3. Nombre: `customer-service-chat-backend`
4. Visibility: **Private**
5. Tag immutability: Opcional (recomendado para producción)
6. Click **"Create repository"**

#### Opción 2: Desde CLI

```bash
# Crear repositorio
aws ecr create-repository \
  --repository-name customer-service-chat-backend \
  --region us-east-1 \
  --image-scanning-configuration scanOnPush=true \
  --encryption-configuration encryptionType=AES256

# Verificar que se creó
aws ecr describe-repositories --repository-names customer-service-chat-backend
```

### Obtener URI del Repositorio:

```bash
# Obtener URI completo del repositorio
aws ecr describe-repositories \
  --repository-names customer-service-chat-backend \
  --query 'repositories[0].repositoryUri' \
  --output text

# Ejemplo de salida:
# 123456789012.dkr.ecr.us-east-1.amazonaws.com/customer-service-chat-backend
```

**Guarda este URI**, lo necesitarás para hacer push de la imagen.

---

## Subir Imagen a ECR

### 1. Autenticar Docker con ECR:

```bash
# Obtener token de autenticación y hacer login
aws ecr get-login-password --region us-east-1 | \
  docker login --username AWS --password-stdin \
  123456789012.dkr.ecr.us-east-1.amazonaws.com

# Reemplaza:
# - us-east-1 con tu región
# - 123456789012 con tu Account ID
```

**Nota:** Este comando expira después de 12 horas. Deberás ejecutarlo cada vez que quieras hacer push.

### 2. Etiquetar la imagen con el URI de ECR:

```bash
# Formato: docker tag <imagen-local> <uri-ecr>:<tag>
docker tag customer-service-chat-backend:1.0.0 \
  123456789012.dkr.ecr.us-east-1.amazonaws.com/customer-service-chat-backend:1.0.0

# También etiquetar como latest
docker tag customer-service-chat-backend:1.0.0 \
  123456789012.dkr.ecr.us-east-1.amazonaws.com/customer-service-chat-backend:latest
```

### 3. Hacer push de la imagen:

```bash
# Push de versión específica
docker push \
  123456789012.dkr.ecr.us-east-1.amazonaws.com/customer-service-chat-backend:1.0.0

# Push de latest
docker push \
  123456789012.dkr.ecr.us-east-1.amazonaws.com/customer-service-chat-backend:latest
```

**Tiempo estimado:** 2-5 minutos dependiendo del tamaño de la imagen.

### 4. Verificar en AWS Console:

1. Ve a **ECR** → **Repositories** → `customer-service-chat-backend`
2. Deberías ver tu imagen con el tag `1.0.0` y `latest`

### 5. Verificar desde CLI:

```bash
# Listar imágenes en el repositorio
aws ecr list-images \
  --repository-name customer-service-chat-backend \
  --region us-east-1

# Ver detalles de una imagen específica
aws ecr describe-images \
  --repository-name customer-service-chat-backend \
  --image-ids imageTag=1.0.0 \
  --region us-east-1
```

---

## Comandos Útiles

### Script de Automatización Completo:

Crea un archivo `deploy-to-ecr.sh`:

```bash
#!/bin/bash

# Configuración
AWS_REGION="us-east-1"
AWS_ACCOUNT_ID="123456789012"  # Reemplaza con tu Account ID
REPOSITORY_NAME="customer-service-chat-backend"
IMAGE_TAG="1.0.0"

# URI completo del repositorio
ECR_URI="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${REPOSITORY_NAME}"

echo "🔨 Construyendo imagen Docker..."
docker build -t ${REPOSITORY_NAME}:${IMAGE_TAG} -t ${REPOSITORY_NAME}:latest .

echo "🔐 Autenticando con ECR..."
aws ecr get-login-password --region ${AWS_REGION} | \
  docker login --username AWS --password-stdin ${ECR_URI}

echo "🏷️  Etiquetando imagen..."
docker tag ${REPOSITORY_NAME}:${IMAGE_TAG} ${ECR_URI}:${IMAGE_TAG}
docker tag ${REPOSITORY_NAME}:latest ${ECR_URI}:latest

echo "📤 Subiendo imagen a ECR..."
docker push ${ECR_URI}:${IMAGE_TAG}
docker push ${ECR_URI}:latest

echo "✅ Imagen subida exitosamente!"
echo "URI: ${ECR_URI}:${IMAGE_TAG}"
```

**Uso:**
```bash
# Hacer ejecutable
chmod +x deploy-to-ecr.sh

# Ejecutar
./deploy-to-ecr.sh
```

### Otros Comandos Útiles:

```bash
# Ver tamaño de imágenes
docker images --format "table {{.Repository}}\t{{.Tag}}\t{{.Size}}"

# Limpiar imágenes no usadas
docker image prune -a

# Limpiar todo (¡cuidado!)
docker system prune -a

# Ver historial de una imagen
docker history customer-service-chat-backend:1.0.0

# Inspeccionar imagen
docker inspect customer-service-chat-backend:1.0.0

# Ejecutar contenedor con variables de entorno desde archivo
docker run -p 8000:8000 --env-file .env customer-service-chat-backend:1.0.0

# Ejecutar contenedor en modo detached (background)
docker run -d -p 8000:8000 --name backend customer-service-chat-backend:1.0.0

# Ver logs en tiempo real
docker logs -f backend

# Detener y eliminar contenedor
docker stop backend && docker rm backend

# Copiar archivo desde contenedor
docker cp backend:/app/logs.txt ./logs.txt

# Copiar archivo al contenedor
docker cp ./config.json backend:/app/config.json
```

---

## Troubleshooting

### Problema: "Cannot connect to Docker daemon"

**Solución:**
```bash
# Verificar que Docker Desktop está corriendo
open /Applications/Docker.app

# Verificar estado
docker info
```

### Problema: "denied: Your Authorization Token has expired"

**Solución:**
```bash
# Re-autenticar con ECR
aws ecr get-login-password --region us-east-1 | \
  docker login --username AWS --password-stdin \
  123456789012.dkr.ecr.us-east-1.amazonaws.com
```

### Problema: "no space left on device"

**Solución:**
```bash
# Limpiar imágenes y contenedores no usados
docker system prune -a

# Ver uso de disco
docker system df
```

### Problema: "Error pulling image" o "manifest unknown"

**Solución:**
```bash
# Verificar que el tag existe en ECR
aws ecr describe-images \
  --repository-name customer-service-chat-backend \
  --image-ids imageTag=1.0.0

# Verificar región correcta
aws ecr describe-repositories --region us-east-1
```

### Problema: La aplicación no puede conectarse a la base de datos

**Solución:**
- Verificar que las variables de entorno están configuradas
- Verificar que el contenedor puede alcanzar la base de datos (red/VPC)
- Verificar seguridad de grupos en AWS

### Problema: "ModuleNotFoundError" al ejecutar el contenedor

**Solución:**
```bash
# Verificar que requirements.txt está actualizado
# Reconstruir la imagen
docker build --no-cache -t customer-service-chat-backend:1.0.0 .
```

---

## Próximos Pasos

Una vez que tengas la imagen en ECR, puedes:

1. **Desplegar en AWS App Runner** (recomendado para aplicaciones web)
2. **Desplegar en ECS (Elastic Container Service)** con Fargate
3. **Desplegar en EC2** con Docker
4. **Desplegar en Lambda** (con contenedores)

### Para AWS App Runner:

La imagen de ECR se puede usar directamente en App Runner. Solo necesitas:
- URI de la imagen ECR
- Variables de entorno configuradas en App Runner
- Configuración de puerto (8000)

---

## Recursos Adicionales

- [Documentación oficial de Docker](https://docs.docker.com/)
- [Documentación de AWS ECR](https://docs.aws.amazon.com/ecr/)
- [Dockerfile Best Practices](https://docs.docker.com/develop/develop-images/dockerfile_best-practices/)
- [AWS ECR User Guide](https://docs.aws.amazon.com/ecr/latest/userguide/)

---

## Checklist Final

Antes de desplegar, verifica:

- [ ] Docker Desktop instalado y corriendo
- [ ] Dockerfile creado y probado localmente
- [ ] Imagen construida exitosamente (`docker build`)
- [ ] Imagen probada localmente (`docker run`)
- [ ] AWS CLI configurado (`aws configure`)
- [ ] Repositorio ECR creado
- [ ] Autenticación con ECR exitosa (`aws ecr get-login-password`)
- [ ] Imagen etiquetada correctamente (`docker tag`)
- [ ] Imagen subida a ECR (`docker push`)
- [ ] Imagen visible en AWS Console

---

¡Listo! Ahora tienes todo lo necesario para crear y subir tu imagen Docker a AWS ECR. 🚀

