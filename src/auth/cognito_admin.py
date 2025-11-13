# src/auth/cognito_admin.py
from typing import List, Literal, Optional, Tuple

import boto3
from botocore.exceptions import ClientError

from config.settings import cognito_config

Role = Literal["Agent", "Supervisor"]

cognito = boto3.client("cognito-idp", region_name=cognito_config.region)



def find_cognito_username_by_email(user_pool_id: str, email: str) -> Optional[str]:
    print(f"[DEBUG cognito_admin] find_cognito_username_by_email: user_pool_id={user_pool_id}, email={email}")
    try:
        resp = cognito.list_users(
            UserPoolId=user_pool_id,
            Filter=f'email = "{email.lower()}"',
            Limit=1
        )
        users = resp.get("Users", [])
        username = users[0]["Username"] if users else None
        print(f"[DEBUG cognito_admin] find_cognito_username_by_email: found username={username}, users_count={len(users)}")
        return username
    except Exception as e:
        print(f"[DEBUG cognito_admin] find_cognito_username_by_email ERROR: {type(e).__name__}: {e}")
        raise


def get_cognito_groups(user_pool_id: str, username: str) -> List[str]:
    print(f"[DEBUG cognito_admin] get_cognito_groups: user_pool_id={user_pool_id}, username={username}")
    groups = []
    try:
        paginator = cognito.get_paginator("admin_list_groups_for_user")
        for page in paginator.paginate(UserPoolId=user_pool_id, Username=username):
            groups.extend(g["GroupName"] for g in page.get("Groups", []))
        print(f"[DEBUG cognito_admin] get_cognito_groups: found groups={groups}")
        return groups
    except Exception as e:
        print(f"[DEBUG cognito_admin] get_cognito_groups ERROR: {type(e).__name__}: {e}")
        raise


def set_cognito_role(user_pool_id: str, username: str, target: Role) -> Tuple[List[str], List[str], bool]:
    """
    Aplica el rol objetivo en Cognito:
    - añade target si falta
    - quita el otro si existe
    Devuelve (before_groups, after_groups, changed)
    """
    print(f"[DEBUG cognito_admin] set_cognito_role: user_pool_id={user_pool_id}, username={username}, target={target}")
    before = get_cognito_groups(user_pool_id, username)
    desired = target
    undesired = "Supervisor" if target == "Agent" else "Agent"
    print(f"[DEBUG cognito_admin] set_cognito_role: before={before}, desired={desired}, undesired={undesired}")

    changed = False
    try:
        if desired not in before:
            print(f"[DEBUG cognito_admin] set_cognito_role: Adding user to group '{desired}'")
            cognito.admin_add_user_to_group(UserPoolId=user_pool_id, Username=username, GroupName=desired)
            changed = True
            print(f"[DEBUG cognito_admin] set_cognito_role: Successfully added to '{desired}'")
        if undesired in before:
            print(f"[DEBUG cognito_admin] set_cognito_role: Removing user from group '{undesired}'")
            cognito.admin_remove_user_from_group(UserPoolId=user_pool_id, Username=username, GroupName=undesired)
            changed = True
            print(f"[DEBUG cognito_admin] set_cognito_role: Successfully removed from '{undesired}'")
    except ClientError as e:
        msg = e.response.get("Error", {}).get("Message", str(e))
        print(f"[DEBUG cognito_admin] set_cognito_role ERROR: {msg}, response={e.response}")
        raise RuntimeError(f"Cognito sync error: {msg}")

    after = get_cognito_groups(user_pool_id, username)
    print(f"[DEBUG cognito_admin] set_cognito_role: after={after}, changed={changed}")
    return before, after, changed


def global_sign_out(user_pool_id: str, username: str) -> None:
    # Invalida refresh tokens; los ID/Access actuales expirarán solos.
    print(f"[DEBUG cognito_admin] global_sign_out: user_pool_id={user_pool_id}, username={username}")
    try:
        cognito.admin_user_global_sign_out(UserPoolId=user_pool_id, Username=username)
        print(f"[DEBUG cognito_admin] global_sign_out: Successfully signed out user")
    except Exception as e:
        print(f"[DEBUG cognito_admin] global_sign_out ERROR: {type(e).__name__}: {e}")
        raise


def disable_cognito_user(user_pool_id: str, username: str) -> None:
    """
    Deshabilita un usuario en Cognito.
    Un usuario deshabilitado no puede iniciar sesión.
    """
    print(f"[DEBUG cognito_admin] disable_cognito_user: user_pool_id={user_pool_id}, username={username}")
    try:
        cognito.admin_disable_user(UserPoolId=user_pool_id, Username=username)
        print(f"[DEBUG cognito_admin] disable_cognito_user: Successfully disabled user")
    except ClientError as e:
        error_code = e.response.get("Error", {}).get("Code", "")
        error_msg = e.response.get("Error", {}).get("Message", str(e))
        print(f"[DEBUG cognito_admin] disable_cognito_user ERROR: {error_code} - {error_msg}")
        raise RuntimeError(f"Error deshabilitando usuario en Cognito: {error_msg}")
    except Exception as e:
        print(f"[DEBUG cognito_admin] disable_cognito_user ERROR: {type(e).__name__}: {e}")
        raise


def enable_cognito_user(user_pool_id: str, username: str) -> None:
    """
    Habilita un usuario en Cognito.
    Un usuario habilitado puede iniciar sesión.
    """
    print(f"[DEBUG cognito_admin] enable_cognito_user: user_pool_id={user_pool_id}, username={username}")
    try:
        cognito.admin_enable_user(UserPoolId=user_pool_id, Username=username)
        print(f"[DEBUG cognito_admin] enable_cognito_user: Successfully enabled user")
    except ClientError as e:
        error_code = e.response.get("Error", {}).get("Code", "")
        error_msg = e.response.get("Error", {}).get("Message", str(e))
        print(f"[DEBUG cognito_admin] enable_cognito_user ERROR: {error_code} - {error_msg}")
        raise RuntimeError(f"Error habilitando usuario en Cognito: {error_msg}")
    except Exception as e:
        print(f"[DEBUG cognito_admin] enable_cognito_user ERROR: {type(e).__name__}: {e}")
        raise

