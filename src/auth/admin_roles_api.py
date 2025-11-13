# src/auth/admin_roles_api.py
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from auth.deps import require_supervisor
from services.role_sync_service import promote_or_demote, repair_to_db_role, Role
from database.db_utils import get_db_connection
from auth.cognito_admin import find_cognito_username_by_email, get_cognito_groups
from config.settings import cognito_config

router = APIRouter(prefix="/admin/roles", tags=["admin"])


class ChangeRolePayload(BaseModel):
    email: str
    role: Role
    force_logout: bool = True


@router.post("/change")
def change_role(payload: ChangeRolePayload, user=Depends(require_supervisor)):
    print(f"[DEBUG admin_roles_api] POST /admin/roles/change: admin={user['email']}, payload={payload}")
    try:
        res = promote_or_demote(
            admin_email=user["email"],
            target_email=str(payload.email),
            target_role=payload.role,
            force_logout=payload.force_logout
        )
        print(f"[DEBUG admin_roles_api] POST /admin/roles/change: success, result={res}")
        return {"success": True, **res}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal server error") from e


class RepairRolePayload(BaseModel):
    email: str
    force_logout: bool = True


@router.post("/repair")
def repair_role(payload: RepairRolePayload, user=Depends(require_supervisor)):
    print(f"[DEBUG admin_roles_api] POST /admin/roles/repair: admin={user['email']}, payload={payload}")
    try:
        res = repair_to_db_role(user["email"], str(payload.email), force_logout=payload.force_logout)
        print(f"[DEBUG admin_roles_api] POST /admin/roles/repair: success, result={res}")
        return {"success": True, **res}
    except ValueError as e:
        print(f"[DEBUG admin_roles_api] POST /admin/roles/repair ERROR: {type(e).__name__}: {e}")
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        print(f"[DEBUG admin_roles_api] POST /admin/roles/repair ERROR: {type(e).__name__}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.get("/inspect")
def inspect(email: str = Query(...), user=Depends(require_supervisor)):
    print(f"[DEBUG admin_roles_api] GET /admin/roles/inspect: admin={user['email']}, email={email}")
    pool = cognito_config.user_pool_id
    e = str(email).lower()
    print(f"[DEBUG admin_roles_api] inspect: user_pool_id={pool}, email={e}")

    # DB
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT role, status FROM invited_users WHERE email = %s", (e,))
            row = cur.fetchone()
            db = {"role": row[0], "status": row[1]} if row else None
            print(f"[DEBUG admin_roles_api] inspect: DB result={db}")
    finally:
        conn.close()

    # Cognito
    username = find_cognito_username_by_email(pool, e)
    groups = get_cognito_groups(pool, username) if username else []
    print(f"[DEBUG admin_roles_api] inspect: Cognito username={username}, groups={groups}")

    result = {
        "email": e,
        "db": db,
        "cognito": {"username": username, "groups": groups},
        "in_sync": bool(db and (db["role"] in groups or username is None))
    }
    print(f"[DEBUG admin_roles_api] inspect: result={result}")
    return result

