# Variables de Entorno - Backend

## Archivo: `.env`

Agrega estas variables de Cognito a tu archivo `.env` del backend (además de las que ya tienes):

```env
# AWS Cognito Authentication Configuration
COGNITO_USER_POOL_ID=us-east-1_WcnMdx46J
COGNITO_REGION=us-east-1
COGNITO_CLIENT_ID=<APP_CLIENT_ID>
COGNITO_JWKS_URL=https://cognito-idp.us-east-1.amazonaws.com/us-east-1_WcnMdx46J/.well-known/jwks.json

# Access Control - Cognito Integration (ya deberías tener estas)
APP_BASE_URL=http://localhost:3000
COGNITO_TRIGGER_KEY=super-secreto-largo
INVITE_TTL_DAYS=7
```

### Ejemplo completo con tus valores:

```env
# Base de datos PostgreSQL
DB_HOST=localhost
DB_PORT=5432
DB_NAME=your_database_name
DB_USER=your_database_user
DB_PASSWORD=your_database_password

# AWS Bedrock
AWS_ACCESS_KEY_ID=your_aws_access_key
AWS_SECRET_ACCESS_KEY=your_aws_secret_key
AWS_REGION=us-east-1
BEDROCK_AGENT_ID=PJSUJU8ACS
BEDROCK_AGENT_ALIAS_ID=customer-service
BEDROCK_AGENT_ARN=arn:aws:bedrock:us-east-1:792655899277:agent/PJSUJU8ACS

# HubSpot
HUBSPOT_TOKEN=your_hubspot_token
HUBSPOT_BASE_URL=https://api.hubapi.com

# AWS Cognito Authentication
COGNITO_USER_POOL_ID=us-east-1_WcnMdx46J
COGNITO_REGION=us-east-1
COGNITO_CLIENT_ID=<tu_app_client_id>
COGNITO_JWKS_URL=https://cognito-idp.us-east-1.amazonaws.com/us-east-1_WcnMdx46J/.well-known/jwks.json

# Access Control - Cognito Integration
APP_BASE_URL=http://localhost:3000
COGNITO_TRIGGER_KEY=super-secreto-largo
INVITE_TTL_DAYS=7
```

## Cómo obtener los valores:

1. **COGNITO_USER_POOL_ID**: 
   - Ve a AWS Console → Cognito → User Pools
   - Copia el Pool ID (ejemplo: `us-east-1_WcnMdx46J`)

2. **COGNITO_REGION**:
   - La región donde está tu User Pool (ejemplo: `us-east-1`)

3. **COGNITO_CLIENT_ID**:
   - En el User Pool → "App integration" → "App clients"
   - Copia el "Client ID" (debe ser el mismo que en el frontend)

4. **COGNITO_JWKS_URL**:
   - Formato: `https://cognito-idp.<region>.amazonaws.com/<USER_POOL_ID>/.well-known/jwks.json`
   - También puedes encontrarlo en: User Pool → "App integration" → "Domain" → "Signing key URL"
   - Ejemplo: `https://cognito-idp.us-east-1.amazonaws.com/us-east-1_WcnMdx46J/.well-known/jwks.json`

5. **COGNITO_TRIGGER_KEY**:
   - Genera una clave secreta larga (ejemplo: `super-secreto-largo-123456789`)
   - Esta clave se usará para validar requests desde la Lambda de Cognito

## Notas importantes:

- ✅ **COGNITO_CLIENT_ID** debe ser el mismo en frontend y backend
- ✅ **COGNITO_JWKS_URL** debe apuntar al endpoint correcto de tu User Pool
- ✅ **COGNITO_TRIGGER_KEY** debe ser seguro y único (usa AWS Secrets Manager en producción)
- ✅ Reemplaza `<tu_app_client_id>` con el valor real de tu App Client ID

