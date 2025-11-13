# Documentación Completa: Autenticación, Tokens y Cookies

## Tabla de Contenidos

1. [Resumen Ejecutivo](#resumen-ejecutivo)
2. [Flujo de Inicio de Sesión](#flujo-de-inicio-de-sesión)
3. [Tokens JWT y Cognito](#tokens-jwt-y-cognito)
4. [Cookies y Almacenamiento](#cookies-y-almacenamiento)
5. [Validación de Tokens](#validación-de-tokens)
6. [Flujo de Invitaciones](#flujo-de-invitaciones)
7. [Expiración y Renovación](#expiración-y-renovación)
8. [Cierre de Sesión](#cierre-de-sesión)
9. [Seguridad y Validaciones](#seguridad-y-validaciones)
10. [Diagramas de Flujo](#diagramas-de-flujo)

---

## Resumen Ejecutivo

El sistema utiliza **Amazon Cognito** para autenticación OAuth2/OIDC con Google como proveedor de identidad. El flujo completo incluye:

- **Autenticación**: OAuth2 Authorization Code Flow con Cognito
- **Token Principal**: `id_token` (JWT) almacenado en cookie HttpOnly
- **Validación**: Verificación de firma, expiración, audiencia e issuer en cada request
- **Autorización**: Basada en grupos de Cognito (`Agent`, `Supervisor`) y allowlist en base de datos
- **Invitaciones**: Sistema de invitaciones con tokens temporales antes del registro

---

## Flujo de Inicio de Sesión

### 1. Inicio del Flujo OAuth

**Frontend → Cognito**

El usuario es redirigido a Cognito para iniciar sesión:

```
GET https://{COGNITO_DOMAIN}/oauth2/authorize?
  client_id={CLIENT_ID}
  &response_type=code
  &redirect_uri={REDIRECT_URI}
  &scope=openid+email+profile
```

**Parámetros importantes:**
- `client_id`: ID del cliente OAuth configurado en Cognito
- `redirect_uri`: URL de callback (ej: `http://localhost:3000/login/callback`)
- `scope`: `openid email profile` (requerido para obtener `id_token`)

### 2. Autenticación con Google

Cognito redirige al usuario a Google para autenticación. El usuario:
1. Inicia sesión con su cuenta de Google
2. Autoriza la aplicación
3. Google redirige de vuelta a Cognito

### 3. Cognito Genera Authorization Code

Después de la autenticación exitosa, Cognito redirige al frontend con un `code`:

```
GET {REDIRECT_URI}?code={AUTHORIZATION_CODE}
```

**Características del código:**
- Es un código de un solo uso
- Expira en ~10 minutos
- Solo puede usarse una vez
- Debe intercambiarse inmediatamente por tokens

### 4. Intercambio de Código por Tokens

**Frontend → Backend → Cognito**

El frontend envía el código al backend:

```http
POST /auth/exchange
Content-Type: application/x-www-form-urlencoded

code={AUTHORIZATION_CODE}
```

**Backend (`main.py:246-291`):**

```python
@app.post("/auth/exchange")
async def auth_exchange(code: str = Form(...)):
    # 1. Intercambiar código por tokens con Cognito
    tokens = exchange_code_for_tokens(code)
    id_token = tokens.get("id_token")
    
    # 2. Validar inmediatamente el token
    claims = verify_id_token(id_token)
    email = (claims.get("email") or "").lower()
    
    # 3. Obtener tiempo de expiración real del token
    token_max_age = get_token_expiration_seconds(id_token)
    
    # 4. Establecer cookie HttpOnly con el id_token
    response.set_cookie(
        key="id_token",
        value=id_token,
        httponly=True,
        secure=COOKIE_SECURE,
        samesite=COOKIE_SAMESITE,
        domain=None if COOKIE_DOMAIN == "localhost" else COOKIE_DOMAIN,
        max_age=token_max_age,  # Sincronizado con expiración del JWT
        path="/",
    )
    
    return {"ok": True, "email": email}
```

**Función `exchange_code_for_tokens` (`cognito.py:68-97`):**

```python
def exchange_code_for_tokens(code: str) -> Dict[str, Any]:
    token_url = f"{DOMAIN}/oauth2/token"
    
    data = {
        "grant_type": "authorization_code",
        "client_id": CLIENT_ID,
        "code": code,
        "redirect_uri": REDIRECT_URI,
    }
    
    # Si hay CLIENT_SECRET, usar Basic Auth
    if CLIENT_SECRET:
        joined = f"{CLIENT_ID}:{CLIENT_SECRET}".encode()
        auth = base64.b64encode(joined).decode()
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Authorization": f"Basic {auth}",
        }
    
    r = requests.post(token_url, data=data, headers=headers, timeout=10)
    return r.json()  # Retorna: id_token, access_token, refresh_token, expires_in
```

**Respuesta de Cognito:**

```json
{
  "id_token": "eyJraWQiOiJ...",
  "access_token": "eyJraWQiOiJ...",
  "refresh_token": "eyJjdHkiOiJ...",
  "token_type": "Bearer",
  "expires_in": 3600
}
```

### 5. Almacenamiento del Token

El backend establece una **cookie HttpOnly** con el `id_token`:

**Configuración de la Cookie (`main.py:44-47`):**

```python
COOKIE_DOMAIN = get_secret("COOKIE_DOMAIN", "localhost") or "localhost"
COOKIE_SECURE = (get_secret("COOKIE_SECURE", "false") or "false").lower() == "true"
COOKIE_SAMESITE = get_secret("COOKIE_SAMESITE", "lax") or "lax"
```

**Parámetros de la Cookie:**

| Parámetro | Valor | Descripción |
|-----------|-------|-------------|
| `key` | `"id_token"` | Nombre de la cookie |
| `value` | `id_token` (JWT completo) | Token JWT firmado por Cognito |
| `httponly` | `True` | **CRÍTICO**: Previene acceso desde JavaScript (protección XSS) |
| `secure` | `COOKIE_SECURE` | Solo envía sobre HTTPS en producción |
| `samesite` | `"lax"` | Protección CSRF (permite navegación normal) |
| `domain` | `COOKIE_DOMAIN` | Dominio donde la cookie es válida |
| `max_age` | `token_max_age` | **Sincronizado con expiración del JWT** |
| `path` | `"/"` | Disponible en todas las rutas |

**¿Por qué `id_token` y no `access_token`?**

- `id_token`: Contiene información del usuario (email, grupos, sub)
- `access_token`: Para llamar a APIs de recursos (no necesario aquí)
- El `id_token` es suficiente para autenticación y autorización en este sistema

---

## Tokens JWT y Cognito

### Estructura del ID Token

El `id_token` es un **JWT (JSON Web Token)** con tres partes:

```
header.payload.signature
```

**1. Header (decodificado):**

```json
{
  "kid": "abc123...",
  "alg": "RS256"
}
```

- `kid`: Key ID para identificar la clave pública en JWKS
- `alg`: Algoritmo de firma (RS256 = RSA con SHA-256)

**2. Payload (claims decodificados):**

```json
{
  "sub": "usuario-uuid",
  "email": "usuario@musclepoints.com",
  "email_verified": true,
  "cognito:groups": ["Agent", "Supervisor"],
  "iss": "https://cognito-idp.us-east-1.amazonaws.com/USER_POOL_ID",
  "aud": "CLIENT_ID",
  "exp": 1234567890,
  "iat": 1234564290,
  "token_use": "id"
}
```

**Claims importantes:**

| Claim | Descripción | Uso |
|-------|-------------|-----|
| `sub` | Subject (ID único del usuario) | Identificación única |
| `email` | Email del usuario | Validación de dominio y allowlist |
| `email_verified` | Si el email está verificado | Validación de seguridad |
| `cognito:groups` | Grupos del usuario | Autorización (Agent/Supervisor) |
| `iss` | Issuer (Cognito) | Validación de origen |
| `aud` | Audience (client_id) | Validación de destinatario |
| `exp` | Expiration timestamp | **Validación de expiración** |
| `iat` | Issued at timestamp | Validación de tiempo |
| `token_use` | Tipo de token (`id`) | Validación de uso |

**3. Signature:**

Firma RSA-256 verificada contra las claves públicas de Cognito (JWKS).

### Validación del Token

**Función `verify_id_token` (`cognito.py:100-118`):**

```python
def verify_id_token(id_token: str) -> Dict[str, Any]:
    """
    Verifica y decodifica el id_token de Cognito.
    Valida: firma, audiencia, issuer, y expiración (exp).
    """
    # 1. Obtener header para extraer kid
    headers = jwt.get_unverified_header(id_token)
    key = _get_key(headers["kid"])  # Obtener clave pública desde JWKS
    
    # 2. Decodificar y validar
    claims = jwt.decode(
        id_token,
        key,
        algorithms=["RS256"],
        audience=CLIENT_ID,     # aud debe ser tu client_id
        issuer=ISSUER,         # issuer debe ser Cognito
        options={
            "verify_at_hash": False,
            "verify_exp": True,  # CRÍTICO: Validar expiración explícitamente
        },
    )
    return claims
```

**Validaciones realizadas:**

1. ✅ **Firma**: Verifica que el token fue firmado por Cognito usando RS256
2. ✅ **Audiencia (`aud`)**: Debe coincidir con `CLIENT_ID`
3. ✅ **Issuer (`iss`)**: Debe ser `https://cognito-idp.{REGION}.amazonaws.com/{USER_POOL_ID}`
4. ✅ **Expiración (`exp`)**: Verifica que el token no haya expirado
5. ✅ **Formato**: Valida que sea un JWT válido

**Obtención de Claves Públicas (JWKS):**

```python
@lru_cache(maxsize=1)
def _fetch_jwks() -> Dict[str, Any]:
    """Obtiene y cachea las claves públicas (JWKS) de Cognito."""
    JWKS_URL = f"{ISSUER}/.well-known/jwks.json"
    r = requests.get(JWKS_URL, timeout=5)
    return r.json()
```

- Las claves se cachean con `@lru_cache` para eficiencia
- Si una clave no se encuentra, se refresca el cache automáticamente
- URL estándar: `https://cognito-idp.{region}.amazonaws.com/{user_pool_id}/.well-known/jwks.json`

---

## Cookies y Almacenamiento

### Cookie `id_token`

**Nombre:** `id_token` (definido en `deps.py:8`)

```python
COOKIE_NAME = "id_token"  # simple: usamos el id_token
```

### Lectura del Token en Requests

**Función `_read_token_from_request` (`deps.py:11-20`):**

```python
def _read_token_from_request(req: Request) -> str:
    # 1) Header Authorization: Bearer <token> (opcional)
    auth = req.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:]
    
    # 2) Cookie HttpOnly (preferido)
    token = req.cookies.get(COOKIE_NAME)
    if token:
        return token
    
    raise HTTPException(status_code=401, detail="Missing token")
```

**Orden de prioridad:**

1. **Header `Authorization: Bearer <token>`** (opcional, para APIs)
2. **Cookie `id_token`** (preferido para navegador)

### Características de Seguridad

**HttpOnly:**
- ✅ La cookie NO es accesible desde JavaScript (`document.cookie`)
- ✅ Protege contra ataques XSS
- ✅ Solo el navegador puede enviarla automáticamente

**SameSite:**
- `"lax"`: Permite navegación normal, bloquea CSRF en POST cross-site
- Protege contra ataques CSRF

**Secure (en producción):**
- ✅ Solo se envía sobre HTTPS
- ✅ Previene interceptación en redes no seguras

**Domain:**
- En desarrollo: `None` (localhost)
- En producción: Dominio específico (ej: `.musclepoints.com`)

### Sincronización de Expiración

**Función `get_token_expiration_seconds` (`cognito.py:121-144`):**

```python
def get_token_expiration_seconds(id_token: str) -> int:
    """
    Obtiene los segundos hasta la expiración del token.
    Retorna el tiempo restante en segundos, o 0 si ya expiró.
    """
    # Decodificar sin verificar para obtener claims
    unverified_claims = jwt.get_unverified_claims(id_token)
    exp = unverified_claims.get("exp")
    
    if not exp:
        return 3600  # Default: 1 hora
    
    current_time = int(time.time())
    remaining = exp - current_time
    
    # Si ya expiró o queda menos de 60 segundos, retornar 0
    # (60 segundos de margen para evitar problemas de sincronización)
    return max(0, remaining - 60)
```

**Importante:**
- La cookie expira **sincronizada** con el JWT
- Se resta 60 segundos de margen para evitar problemas de sincronización de reloj
- Si el token ya expiró, la cookie también expira inmediatamente

---

## Validación de Tokens

### Flujo de Validación en Cada Request

**Dependency `current_user` (`deps.py:42-56`):**

```python
def current_user(req: Request) -> Dict[str, Any]:
    # 1. Leer token desde request
    token = _read_token_from_request(req)
    
    # 2. Verificar firma, expiración, issuer, audiencia
    claims = verify_id_token(token)
    
    # 3. Extraer y validar email
    email = (claims.get("email") or "").lower()
    if not email or not is_allowed_email(email):
        raise HTTPException(status_code=403, detail="Email domain not allowed")
    
    # 4. Extraer grupos
    groups_list = extract_groups(claims)
    groups_set = set(groups_list)
    
    # 5. Validar que tenga grupo permitido
    if not (groups_set & ALLOWED_GROUPS):
        raise HTTPException(status_code=403, detail="Required group not present")
    
    # 6. Verificar allowlist en base de datos
    _check_allowlist(email)
    
    return {
        "email": email,
        "groups": groups_list,
        "claims": claims
    }
```

### Pasos de Validación Detallados

**1. Lectura del Token:**
- Busca en `Authorization` header o cookie `id_token`
- Si no encuentra, retorna 401 Unauthorized

**2. Verificación JWT (`verify_id_token`):**
- ✅ Firma válida (RS256 con clave pública de Cognito)
- ✅ No expirado (`exp` > tiempo actual)
- ✅ Audiencia correcta (`aud` == `CLIENT_ID`)
- ✅ Issuer correcto (`iss` == Cognito User Pool)

**3. Validación de Email:**
- ✅ Email presente en claims
- ✅ Dominio permitido (`@musclepoints.com`)

**Función `is_allowed_email` (`cognito.py:153-154`):**

```python
def is_allowed_email(email: str) -> bool:
    return email.lower().endswith(f"@{ALLOWED_DOMAIN}")
```

**4. Validación de Grupos:**

**Función `extract_groups` (`cognito.py:147-150`):**

```python
def extract_groups(claims: Dict[str, Any]) -> List[str]:
    g = claims.get("cognito:groups") or []
    return g if isinstance(g, list) else []
```

**Grupos permitidos (`cognito.py:28`):**

```python
ALLOWED_GROUPS = {"Agent", "Supervisor"}
```

- El usuario debe tener al menos uno de estos grupos
- Se retorna la lista completa de grupos (preserva orden)

**5. Validación de Allowlist:**

**Función `_check_allowlist` (`deps.py:22-40`):**

```python
def _check_allowlist(email: str, expected_role: str | None = None) -> None:
    conn = get_db_connection()
    with conn, conn.cursor() as cur:
        cur.execute("""
            SELECT role, status
            FROM invited_users
            WHERE email = %s
        """, (email,))
        row = cur.fetchone()
        
        if not row:
            raise HTTPException(status_code=403, detail="Not invited")
        
        role, status = row
        if status != "active":
            raise HTTPException(status_code=403, detail=f"Invitation status: {status}")
        
        # Validación de rol (si se especifica)
        if expected_role and role != expected_role:
            # Permitimos Supervisor acceder a rutas Agent
            if expected_role == "Agent" and role == "Supervisor":
                return
            raise HTTPException(status_code=403, detail=f"Role mismatch")
```

**Validaciones de allowlist:**
- ✅ Usuario existe en tabla `invited_users`
- ✅ Estado es `"active"` (no `pending` ni `revoked`)
- ✅ Rol coincide (si se especifica `expected_role`)
- ✅ Supervisor puede acceder a rutas de Agent (jerarquía)

### Uso en Endpoints

**Ejemplo: Endpoint protegido (`main.py:92-138`):**

```python
@app.post("/api/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest, me=Depends(current_user)):
    # 'me' contiene: {"email": "...", "groups": [...], "claims": {...}}
    groups = set(me.get("groups", []))
    role = "Supervisor" if "Supervisor" in groups else "Agent"
    
    session_attrs = {
        "role": role,
        "user_email": me["email"],
        "user_id": me["claims"].get("sub", ""),
        "groups": ",".join(groups)
    }
    
    # ... usar session_attrs en llamada a Bedrock
```

**Ejemplo: Endpoint con rol específico (`users_api.py:26-35`):**

```python
@router.get("/users")
def list_users(me=Depends(current_user)):
    groups = set(me.get("groups", []))
    if "Supervisor" not in groups:
        raise HTTPException(status_code=403, detail="Supervisor role required")
    # ... listar usuarios
```

---

## Flujo de Invitaciones

### 1. Creación de Invitación

**Endpoint:** `POST /auth/invite`

**Requisitos:**
- Usuario autenticado con grupo `Supervisor`
- Email del dominio `@musclepoints.com`
- Rol válido: `Agent` o `Supervisor`

**Proceso (`invite_api.py:120-239`):**

```python
@router.post("/invite")
def invite_user(body: InviteBody, me=Depends(current_user)):
    # 1. Validar permisos
    groups = set(me.get("groups", []))
    if "Supervisor" not in groups:
        raise HTTPException(status_code=403, detail="Supervisor role required")
    
    # 2. Generar token de invitación
    token = secrets.token_urlsafe(32)  # Token seguro de 32 bytes
    
    # 3. Calcular expiración
    exp = dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=INVITE_EXP_DAYS)
    # INVITE_EXP_DAYS = 7 días por defecto
    
    # 4. Guardar en base de datos
    # - Si no existe: crear con status='pending'
    # - Si existe pending: regenerar token (renovar expiración)
    # - Si existe active: regenerar token (permitir reenvío)
    # - Si existe revoked: cambiar a pending y generar token
    
    # 5. Enviar email vía n8n
    invite_url = f"{FRONTEND_ACCEPT_URL}?token={token}"
    _send_email_via_n8n(...)
    
    return {
        "ok": True,
        "email": body.email,
        "role": body.role,
        "status": final_status,
        "invite_url": invite_url,
        "expires_at": exp.isoformat(),
        "email_sent": email_sent
    }
```

**Estados de Invitación:**

| Estado | Descripción | Acción Permitida |
|--------|-------------|------------------|
| `pending` | Invitación creada, no aceptada | Usuario puede aceptar |
| `active` | Invitación aceptada, usuario activo | Usuario puede iniciar sesión |
| `revoked` | Invitación revocada | Usuario NO puede iniciar sesión |

**Tabla `invited_users`:**

```sql
CREATE TABLE invited_users (
    email VARCHAR(255) PRIMARY KEY,
    role VARCHAR(50) NOT NULL,  -- 'Agent' | 'Supervisor'
    status VARCHAR(50) NOT NULL, -- 'pending' | 'active' | 'revoked'
    token VARCHAR(255),          -- Token de invitación (NULL después de aceptar)
    token_expires_at TIMESTAMPTZ, -- Expiración del token
    invited_by VARCHAR(255),     -- Email del supervisor que invitó
    created_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ
);
```

### 2. Aceptación de Invitación

**Endpoint:** `POST /auth/accept?token={INVITE_TOKEN}`

**Proceso (`accept_api.py:13-101`):**

```python
@router.post("/accept")
def accept_invite(token: str = Query(...)):
    # 1. Buscar token en base de datos
    cur.execute("""
        SELECT email, status, token_expires_at 
        FROM invited_users 
        WHERE token = %s
    """, (token,))
    
    # 2. Validar token
    if not row:
        raise HTTPException(status_code=400, detail="Token inválido o expirado")
    
    email, current_status, token_expires_at = row
    
    # 3. Verificar expiración
    if token_expires_at and token_expires_at < dt.datetime.now(dt.timezone.utc):
        raise HTTPException(status_code=400, detail="Token expirado")
    
    # 4. Activar usuario
    if current_status == "active":
        # Idempotente: limpiar token pero mantener estado
        cur.execute("""
            UPDATE invited_users 
            SET token = NULL, 
                token_expires_at = NULL,
                updated_at = NOW()
            WHERE email = %s
        """, (email,))
    else:
        # Cambiar a active y limpiar token
        cur.execute("""
            UPDATE invited_users 
            SET status = 'active',
                token = NULL,
                token_expires_at = NULL,
                updated_at = NOW()
            WHERE email = %s AND token = %s
        """, (email, token))
    
    return {
        "ok": True,
        "email": email,
        "message": "Invitación activada correctamente. Ahora puedes iniciar sesión."
    }
```

**Reglas de Idempotencia:**
- ✅ Token válido: cambia status a `active`, limpia token
- ✅ Token ya consumido: 400 Bad Request
- ✅ Token expirado: 400 Bad Request
- ✅ Usuario ya activo: 200 OK (idempotente, limpia token)

### 3. Registro en Cognito

Después de aceptar la invitación, el usuario debe:

1. **Iniciar sesión con Google** vía Cognito
2. **Cognito valida el email** contra la allowlist usando Lambda triggers

**Lambda Triggers de Cognito:**

**Pre Sign-up Lambda:**
- Verifica que el email esté en `invited_users` con status `active`
- Llama a `/internal/allowlist/check` con API key
- Si no está permitido, rechaza el registro

**Post Confirmation Lambda:**
- Asigna grupos de Cognito según el rol en `invited_users`
- Si `role == "Supervisor"` → asigna grupo `Supervisor`
- Si `role == "Agent"` → asigna grupo `Agent`

**Endpoint de Allowlist (`allowlist_check.py:19-76`):**

```python
@router.get("/internal/allowlist/check")
def allowlist_check(
    email: str = Query(...),
    x_api_key: str | None = Header(None, alias="X-API-Key")
):
    # Validar API key
    if not x_api_key or x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    # Buscar en base de datos
    cur.execute("""
        SELECT role, status
        FROM invited_users
        WHERE email = %s
    """, (email_lower,))
    
    row = cur.fetchone()
    if not row:
        return {"allowed": False, "role": None}
    
    role, status = row
    allowed = status == "active"
    
    return {
        "allowed": allowed,
        "role": role
    }
```

---

## Expiración y Renovación

### Expiración del ID Token

**Tiempo de vida por defecto:**
- Cognito: **1 hora (3600 segundos)**
- Configurable en Cognito User Pool settings

**Validación de expiración:**

El token incluye el claim `exp` (expiration timestamp):

```json
{
  "exp": 1234567890,  // Unix timestamp
  "iat": 1234564290   // Issued at timestamp
}
```

**Durante la validación (`cognito.py:107-117`):**

```python
claims = jwt.decode(
    id_token,
    key,
    algorithms=["RS256"],
    audience=CLIENT_ID,
    issuer=ISSUER,
    options={
        "verify_exp": True,  # CRÍTICO: Validar expiración
    },
)
```

Si `exp < tiempo_actual`, `jwt.decode()` lanza excepción → 401 Unauthorized

### Expiración de la Cookie

**Sincronización automática:**

La cookie expira **sincronizada** con el JWT:

```python
token_max_age = get_token_expiration_seconds(id_token)
response.set_cookie(
    key="id_token",
    value=id_token,
    max_age=token_max_age,  # Sincronizado con expiración del JWT
    ...
)
```

**Margen de seguridad:**

Se resta 60 segundos para evitar problemas de sincronización:

```python
remaining = exp - current_time
return max(0, remaining - 60)  # 60 segundos de margen
```

### Renovación del Token

**Opción 1: Refresh Token (no implementado actualmente)**

Cognito también retorna un `refresh_token` que puede usarse para obtener nuevos tokens sin reautenticación:

```python
# Endpoint hipotético (no implementado)
@app.post("/auth/refresh")
async def refresh_token(refresh_token: str = Form(...)):
    token_url = f"{DOMAIN}/oauth2/token"
    data = {
        "grant_type": "refresh_token",
        "client_id": CLIENT_ID,
        "refresh_token": refresh_token,
    }
    # ... intercambiar refresh_token por nuevos tokens
```

**Opción 2: Reautenticación (actual)**

Cuando el token expira:
1. El usuario recibe 401 Unauthorized
2. El frontend redirige a Cognito para reautenticación
3. Se obtiene nuevo `id_token` y se actualiza la cookie

**Detección de expiración en frontend:**

```javascript
// Ejemplo de manejo en frontend
fetch('/api/chat', {
    credentials: 'include'  // Incluye cookie automáticamente
})
.then(response => {
    if (response.status === 401) {
        // Token expirado, redirigir a login
        window.location.href = '/login';
    }
});
```

### Expiración de Token de Invitación

**Tiempo de vida:**
- Por defecto: **7 días** (`INVITE_EXP_DAYS`)
- Configurable vía variable de entorno `INVITE_EXP_DAYS`

**Validación (`accept_api.py:44-46`):**

```python
if token_expires_at and token_expires_at < dt.datetime.now(dt.timezone.utc):
    raise HTTPException(status_code=400, detail="Token expirado")
```

**Renovación:**
- Un Supervisor puede regenerar el token de invitación llamando `/auth/invite` nuevamente
- Esto renueva la expiración por otros 7 días

---

## Cierre de Sesión

### Endpoint de Logout

**Endpoint:** `POST /auth/logout`

**Proceso (`main.py:294-311`):**

```python
@app.post("/auth/logout")
async def auth_logout():
    """
    Cierra sesión completamente:
    1. Elimina la cookie id_token del backend
    2. El frontend redirige a Cognito /logout para cerrar sesión de Cognito
    """
    response = Response(content=json.dumps({"ok": True}), media_type="application/json")
    
    # Eliminar cookie con los mismos parámetros que se usaron para establecerla
    response.delete_cookie(
        key="id_token",
        path="/",
        domain=None if COOKIE_DOMAIN == "localhost" else COOKIE_DOMAIN,
        samesite=COOKIE_SAMESITE,
        secure=COOKIE_SECURE,
        httponly=True,
    )
    return response
```

**Importante:**
- La cookie se elimina con los **mismos parámetros** que se usaron para crearla
- Esto asegura que se elimine correctamente incluso en diferentes dominios

### Flujo Completo de Logout

**1. Backend elimina cookie:**
```
POST /auth/logout
→ Elimina cookie id_token
→ Retorna {"ok": True}
```

**2. Frontend redirige a Cognito:**
```
GET https://{COGNITO_DOMAIN}/logout?
  client_id={CLIENT_ID}
  &logout_uri={FRONTEND_URL}
```

**3. Cognito cierra sesión:**
- Elimina la sesión de Cognito
- Redirige de vuelta al frontend

**4. Frontend redirige a login:**
```
→ Redirige a /login
```

---

## Seguridad y Validaciones

### Capas de Seguridad

**1. Autenticación (¿Quién eres?):**
- ✅ OAuth2 con Google vía Cognito
- ✅ Token JWT firmado por Cognito
- ✅ Validación de firma, expiración, issuer, audiencia

**2. Autorización (¿Qué puedes hacer?):**
- ✅ Grupos de Cognito (`Agent`, `Supervisor`)
- ✅ Allowlist en base de datos (solo usuarios invitados)
- ✅ Validación de dominio de email (`@musclepoints.com`)

**3. Protección de Cookies:**
- ✅ HttpOnly (no accesible desde JavaScript)
- ✅ Secure (solo HTTPS en producción)
- ✅ SameSite (protección CSRF)
- ✅ Expiración sincronizada con JWT

**4. Validación de Invitaciones:**
- ✅ Tokens seguros (`secrets.token_urlsafe(32)`)
- ✅ Expiración configurable (7 días)
- ✅ Estados: pending → active → revoked
- ✅ Validación en Lambda triggers de Cognito

### Validaciones por Capa

**Capa 1: Cognito (OAuth2)**
- ✅ Usuario autenticado con Google
- ✅ Email verificado por Google
- ✅ Token firmado por Cognito

**Capa 2: Backend (JWT)**
- ✅ Firma válida (RS256)
- ✅ No expirado (`exp`)
- ✅ Audiencia correcta (`aud`)
- ✅ Issuer correcto (`iss`)

**Capa 3: Dominio**
- ✅ Email termina en `@musclepoints.com`

**Capa 4: Grupos**
- ✅ Usuario tiene grupo `Agent` o `Supervisor`

**Capa 5: Allowlist**
- ✅ Usuario existe en `invited_users`
- ✅ Estado es `active`
- ✅ Rol coincide (si se especifica)

### Protecciones Adicionales

**Rate Limiting:**
- ⚠️ No implementado actualmente
- Recomendación: Agregar rate limiting en endpoints de autenticación

**CORS:**
- ✅ Configurado para dominios específicos
- ✅ `allow_credentials=True` para cookies

**API Key para Endpoints Internos:**
- ✅ `/internal/allowlist/check` protegido con API key
- ✅ Usado por Lambda triggers de Cognito

**Logging:**
- ✅ Logs de autenticación exitosa/fallida
- ✅ Logs de intentos de acceso no autorizado

---

## Diagramas de Flujo

### Flujo de Inicio de Sesión

```
┌─────────┐
│ Usuario │
└────┬────┘
     │
     │ 1. Click "Login"
     ▼
┌─────────────────┐
│   Frontend      │
│  Redirige a     │
│   Cognito       │
└────┬────────────┘
     │
     │ GET /oauth2/authorize?...
     ▼
┌─────────────────┐
│ Amazon Cognito  │
└────┬────────────┘
     │
     │ Redirige a Google
     ▼
┌─────────────────┐
│     Google      │
│  Autenticación  │
└────┬────────────┘
     │
     │ Usuario autoriza
     ▼
┌─────────────────┐
│ Amazon Cognito  │
│ Genera code     │
└────┬────────────┘
     │
     │ Redirect con code
     ▼
┌─────────────────┐
│   Frontend      │
│  /login/callback│
└────┬────────────┘
     │
     │ POST /auth/exchange
     │ code={code}
     ▼
┌─────────────────┐
│    Backend      │
│  Intercambia    │
│  code → tokens  │
└────┬────────────┘
     │
     │ POST /oauth2/token
     ▼
┌─────────────────┐
│ Amazon Cognito  │
│ Retorna tokens  │
└────┬────────────┘
     │
     │ id_token, access_token, refresh_token
     ▼
┌─────────────────┐
│    Backend      │
│ 1. Verifica     │
│    id_token     │
│ 2. Establece    │
│    cookie       │
└────┬────────────┘
     │
     │ Set-Cookie: id_token=...
     ▼
┌─────────────────┐
│   Frontend      │
│  Cookie guardada│
│  Sesión activa  │
└─────────────────┘
```

### Flujo de Validación en Request

```
┌─────────┐
│ Usuario │
└────┬────┘
     │
     │ GET /api/chat
     │ Cookie: id_token=...
     ▼
┌─────────────────┐
│    Backend      │
│  current_user() │
└────┬────────────┘
     │
     │ 1. Leer token
     ▼
┌─────────────────┐
│  ¿Token existe? │
└────┬────────────┘
     │ NO → 401 Unauthorized
     │ SÍ ↓
     │
     │ 2. Verificar JWT
     ▼
┌─────────────────┐
│ verify_id_token │
│ - Firma         │
│ - Expiración    │
│ - Audiencia     │
│ - Issuer        │
└────┬────────────┘
     │ Inválido → 401
     │ Válido ↓
     │
     │ 3. Validar email
     ▼
┌─────────────────┐
│ ¿Email válido?  │
│ @musclepoints   │
└────┬────────────┘
     │ NO → 403 Forbidden
     │ SÍ ↓
     │
     │ 4. Validar grupos
     ▼
┌─────────────────┐
│ ¿Tiene grupo?   │
│ Agent/Supervisor│
└────┬────────────┘
     │ NO → 403 Forbidden
     │ SÍ ↓
     │
     │ 5. Validar allowlist
     ▼
┌─────────────────┐
│ ¿Está activo?   │
│ status=active   │
└────┬────────────┘
     │ NO → 403 Forbidden
     │ SÍ ↓
     │
     │ Retorna usuario
     ▼
┌─────────────────┐
│   Endpoint      │
│  Ejecuta lógica │
└─────────────────┘
```

### Flujo de Invitaciones

```
┌──────────────┐
│ Supervisor   │
└──────┬───────┘
       │
       │ POST /auth/invite
       │ {email, role}
       ▼
┌─────────────────┐
│    Backend      │
│ 1. Valida       │
│    permisos     │
│ 2. Genera token │
│ 3. Guarda en DB │
└────┬────────────┘
     │
     │ Envía email vía n8n
     ▼
┌─────────────────┐
│      n8n        │
│  Envía email    │
└────┬────────────┘
     │
     │ Email con link
     ▼
┌─────────────────┐
│   Usuario       │
│  Recibe email   │
└────┬────────────┘
     │
     │ Click en link
     │ /invite/accept?token=...
     ▼
┌─────────────────┐
│   Frontend      │
│  Página accept  │
└────┬────────────┘
     │
     │ POST /auth/accept?token=...
     ▼
┌─────────────────┐
│    Backend      │
│ 1. Valida token │
│ 2. Activa user  │
│    status=active│
└────┬────────────┘
     │
     │ Usuario activado
     ▼
┌─────────────────┐
│   Usuario       │
│  Inicia sesión  │
│  con Google     │
└────┬────────────┘
     │
     │ Cognito valida
     │ vía Lambda
     ▼
┌─────────────────┐
│ Lambda Trigger  │
│ /allowlist/check│
└────┬────────────┘
     │
     │ Usuario permitido
     │ Asigna grupos
     ▼
┌─────────────────┐
│   Usuario       │
│  Sesión activa  │
└─────────────────┘
```

---

## Resumen de Configuración

### Variables de Entorno Requeridas

**Cognito:**
- `COGNITO_REGION`: Región de AWS (ej: `us-east-1`)
- `COGNITO_USER_POOL_ID`: ID del User Pool
- `COGNITO_CLIENT_ID`: ID del cliente OAuth
- `COGNITO_CLIENT_SECRET`: Secret del cliente (opcional)
- `COGNITO_DOMAIN`: Dominio de Cognito (ej: `auth.musclepoints.com`)
- `OAUTH_REDIRECT_URI`: URI de callback (ej: `http://localhost:3000/login/callback`)

**Cookies:**
- `COOKIE_DOMAIN`: Dominio de la cookie (ej: `localhost` o `.musclepoints.com`)
- `COOKIE_SECURE`: `true` en producción, `false` en desarrollo
- `COOKIE_SAMESITE`: `lax` (recomendado)

**Invitaciones:**
- `INVITE_EXP_DAYS`: Días de expiración (default: `7`)
- `FRONTEND_ACCEPT_URL`: URL de aceptación (ej: `http://localhost:3000/invite/accept`)
- `N8N_MAIL_WEBHOOK_URL`: URL del webhook de n8n para emails
- `N8N_MAIL_API_KEY`: API key para n8n (opcional)

**Interno:**
- `INGEST_API_KEY`: API key para endpoints internos (`/internal/allowlist/check`)

### Configuración de Cognito

**User Pool Settings:**
- App client con OAuth2 habilitado
- Callback URLs configuradas
- Google como Identity Provider
- Grupos: `Agent`, `Supervisor`

**Lambda Triggers:**
- **Pre Sign-up**: Valida allowlist vía `/internal/allowlist/check`
- **Post Confirmation**: Asigna grupos según rol en `invited_users`

---

## Preguntas Frecuentes

### ¿Por qué usar `id_token` y no `access_token`?

- `id_token` contiene información del usuario (email, grupos) necesaria para autorización
- `access_token` es para llamar a APIs de recursos externos (no necesario aquí)
- El `id_token` es suficiente para autenticación y autorización en este sistema

### ¿Cuánto tiempo dura una sesión?

- El `id_token` expira en **1 hora** (configurable en Cognito)
- La cookie expira sincronizada con el token
- Después de 1 hora, el usuario debe reautenticarse

### ¿Cómo se renueva el token?

- Actualmente no hay renovación automática
- Cuando expira, el usuario debe reautenticarse
- Opción futura: Implementar refresh token

### ¿Qué pasa si el token expira durante una sesión?

- El próximo request retornará 401 Unauthorized
- El frontend debe detectar esto y redirigir a login
- El usuario se reautentica y obtiene nuevo token

### ¿Cómo funciona la allowlist?

- Solo usuarios invitados por un Supervisor pueden registrarse
- El estado debe ser `active` para poder iniciar sesión
- Los estados son: `pending` → `active` → `revoked`

### ¿Qué grupos de Cognito se usan?

- `Agent`: Usuario con rol Agent
- `Supervisor`: Usuario con rol Supervisor (puede acceder a rutas de Agent)

### ¿Cómo se protege contra XSS?

- Cookie `HttpOnly`: No accesible desde JavaScript
- Previene que scripts maliciosos roben el token

### ¿Cómo se protege contra CSRF?

- Cookie `SameSite=lax`: Bloquea requests cross-site maliciosos
- Permite navegación normal pero protege POST cross-site

---

## Referencias

- **Archivos clave:**
  - `src/auth/deps.py`: Validación de tokens y dependencias
  - `src/auth/cognito.py`: Integración con Cognito y verificación JWT
  - `src/auth/invite_api.py`: Sistema de invitaciones
  - `src/auth/accept_api.py`: Aceptación de invitaciones
  - `src/auth/allowlist_check.py`: Validación de allowlist
  - `main.py`: Endpoints de autenticación y configuración de cookies

- **Documentación externa:**
  - [Amazon Cognito OAuth2](https://docs.aws.amazon.com/cognito/latest/developerguide/cognito-user-pools-oauth2-flows.html)
  - [JWT Specification](https://tools.ietf.org/html/rfc7519)
  - [OAuth2 Authorization Code Flow](https://oauth.net/2/grant-types/authorization-code/)

---

**Última actualización:** 2024
**Versión del documento:** 1.0

