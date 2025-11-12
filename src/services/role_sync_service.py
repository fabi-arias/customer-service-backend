# src/services/role_sync_service.py
from typing import Literal, Optional
import json
from database.db_utils import get_db_connection
from auth.cognito_admin import (
    find_cognito_username_by_email, set_cognito_role, get_cognito_groups, global_sign_out
)
from config.settings import cognito_config

Role = Literal["Agent", "Supervisor"]


def _audit_admin_change(conn, admin_email: str, target_email: str, action: str,
                        db_from: Optional[str], db_to: Optional[str],
                        username: Optional[str], after_groups, status_msg: str,
                        tokens_revoked: bool):
    """
    Reutiliza auth_login_events para auditar (sin romper el CHECK).
    - result: 'allowed'
    - provider_sub: 'admin:roles'
    - reason: JSON compacto describiendo la operación
    """
    reason = json.dumps({
        "action": action,
        "db_from": db_from,
        "db_to": db_to,
        "cognito_username": username,
        "cognito_after": after_groups,
        "tokens_revoked": tokens_revoked,
        "status": status_msg,
    }, ensure_ascii=False)

    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO auth_login_events (email, provider_sub, groups, result, reason, user_agent, ip)
            VALUES (%s, %s, %s, %s, %s, %s, NULL)
        """, (target_email.lower(), "admin:roles", after_groups or [], "allowed", reason, f"admin:{admin_email}"))


def promote_or_demote(admin_email: str, target_email: str, target_role: Role,
                      force_logout: bool = True) -> dict:
    """
    Idempotente: pone target_role en DB y en Cognito (si el usuario existe).
    Audita en auth_login_events.
    """
    print(f"[DEBUG role_sync] promote_or_demote START: admin={admin_email}, target={target_email}, role={target_role}, force_logout={force_logout}")
    pool = cognito_config.user_pool_id
    print(f"[DEBUG role_sync] promote_or_demote: user_pool_id={pool}")
    target_email = target_email.lower()

    conn = get_db_connection()
    with conn:
        # 1) Lee/actualiza DB
        with conn.cursor() as cur:
            print(f"[DEBUG role_sync] promote_or_demote: Querying DB for email={target_email}")
            cur.execute("SELECT role FROM invited_users WHERE email = %s", (target_email,))
            row = cur.fetchone()
            if not row:
                print(f"[DEBUG role_sync] promote_or_demote: User not found in DB")
                # Audita intento fallido
                _audit_admin_change(conn, admin_email, target_email, "change:db-miss",
                                    None, target_role, None, [], "user_not_in_DB", False)
                raise ValueError("User not found in invited_users")

            current_db_role = row[0]
            print(f"[DEBUG role_sync] promote_or_demote: DB role={current_db_role}, target_role={target_role}")
            db_changed = current_db_role != target_role
            if db_changed:
                print(f"[DEBUG role_sync] promote_or_demote: Updating DB role from {current_db_role} to {target_role}")
                cur.execute(
                    "UPDATE invited_users SET role = %s, updated_at = NOW() WHERE email = %s",
                    (target_role, target_email)
                )
                print(f"[DEBUG role_sync] promote_or_demote: DB updated successfully")
            else:
                print(f"[DEBUG role_sync] promote_or_demote: DB role already matches, no update needed")

        # 2) Sincroniza Cognito
        print(f"[DEBUG role_sync] promote_or_demote: Looking up Cognito username for email={target_email}")
        username = find_cognito_username_by_email(pool, target_email)
        if not username:
            print(f"[DEBUG role_sync] promote_or_demote: Cognito user not found")
            # Usuario aún no creado/confirmado en Cognito: deja DB lista y audita
            _audit_admin_change(conn, admin_email, target_email, "change:cognito-miss",
                                current_db_role, target_role, None, [],
                                "cognito_user_not_found; DB updated" if db_changed else "noop", False)
            return {
                "ok": True,
                "db_changed": db_changed,
                "cognito_changed": False,
                "tokens_revoked": False,
                "note": "Cognito user not found; will sync on first login"
            }

        print(f"[DEBUG role_sync] promote_or_demote: Found Cognito username={username}, setting role")
        before, after, cg_changed = set_cognito_role(pool, username, target_role)
        print(f"[DEBUG role_sync] promote_or_demote: Cognito sync result: before={before}, after={after}, changed={cg_changed}")

        # 3) Revocación opcional
        tokens_revoked = False
        if force_logout and cg_changed:
            print(f"[DEBUG role_sync] promote_or_demote: Force logout requested, revoking tokens")
            try:
                global_sign_out(pool, username)
                tokens_revoked = True
                print(f"[DEBUG role_sync] promote_or_demote: Tokens revoked successfully")
            except Exception as e:
                print(f"[DEBUG role_sync] promote_or_demote: Token revocation failed: {type(e).__name__}: {e}")
                tokens_revoked = False  # no es crítico

        # 4) Auditoría
        status = "ok" if (db_changed or cg_changed) else "noop"
        print(f"[DEBUG role_sync] promote_or_demote: Auditing change, status={status}")
        _audit_admin_change(conn, admin_email, target_email, "change",
                            current_db_role, target_role, username, after, status, tokens_revoked)

    result = {
        "ok": True,
        "db_changed": db_changed,
        "cognito_changed": cg_changed,
        "tokens_revoked": tokens_revoked
    }
    print(f"[DEBUG role_sync] promote_or_demote END: result={result}")
    return result


def repair_to_db_role(admin_email: str, target_email: str, force_logout: bool = True) -> dict:
    """
    Repara desfasajes: toma el rol fuente de DB y lo aplica a Cognito.
    """
    print(f"[DEBUG role_sync] repair_to_db_role START: admin={admin_email}, target={target_email}, force_logout={force_logout}")
    pool = cognito_config.user_pool_id
    print(f"[DEBUG role_sync] repair_to_db_role: user_pool_id={pool}")
    target_email = target_email.lower()

    conn = get_db_connection()
    with conn:
        # DB: rol fuente
        with conn.cursor() as cur:
            print(f"[DEBUG role_sync] repair_to_db_role: Querying DB for email={target_email}")
            cur.execute("SELECT role FROM invited_users WHERE email = %s", (target_email,))
            row = cur.fetchone()
            if not row:
                print(f"[DEBUG role_sync] repair_to_db_role: User not found in DB")
                _audit_admin_change(conn, admin_email, target_email, "repair:db-miss",
                                    None, None, None, [], "user_not_in_DB", False)
                raise ValueError("User not found in invited_users")
            db_role = row[0]
            print(f"[DEBUG role_sync] repair_to_db_role: DB role={db_role}")

        print(f"[DEBUG role_sync] repair_to_db_role: Looking up Cognito username for email={target_email}")
        username = find_cognito_username_by_email(pool, target_email)
        if not username:
            print(f"[DEBUG role_sync] repair_to_db_role: Cognito user not found")
            _audit_admin_change(conn, admin_email, target_email, "repair:cognito-miss",
                                db_role, db_role, None, [], "cognito_user_not_found", False)
            return {"ok": True, "cognito_changed": False, "tokens_revoked": False, "note": "cognito user not found"}

        print(f"[DEBUG role_sync] repair_to_db_role: Found Cognito username={username}, setting role to {db_role}")
        before, after, cg_changed = set_cognito_role(pool, username, db_role)
        print(f"[DEBUG role_sync] repair_to_db_role: Cognito sync result: before={before}, after={after}, changed={cg_changed}")

        tokens_revoked = False
        if force_logout and cg_changed:
            print(f"[DEBUG role_sync] repair_to_db_role: Force logout requested, revoking tokens")
            try:
                global_sign_out(pool, username)
                tokens_revoked = True
                print(f"[DEBUG role_sync] repair_to_db_role: Tokens revoked successfully")
            except Exception as e:
                print(f"[DEBUG role_sync] repair_to_db_role: Token revocation failed: {type(e).__name__}: {e}")
                tokens_revoked = False

        status = "ok" if cg_changed else "noop"
        print(f"[DEBUG role_sync] repair_to_db_role: Auditing change, status={status}")
        _audit_admin_change(conn, admin_email, target_email, "repair",
                            db_role, db_role, username, after,
                            status, tokens_revoked)

    result = {"ok": True, "cognito_changed": cg_changed, "tokens_revoked": tokens_revoked}
    print(f"[DEBUG role_sync] repair_to_db_role END: result={result}")
    return result

