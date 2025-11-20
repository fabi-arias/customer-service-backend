# src/auth/cognito_admin.py
from typing import List, Literal, Optional, Tuple

import boto3
from botocore.exceptions import ClientError

from config.settings import cognito_config

Role = Literal["Agent", "Supervisor"]

cognito = boto3.client("cognito-idp", region_name=cognito_config.region)



def find_cognito_username_by_email(user_pool_id: str, email: str) -> Optional[str]:
    try:
        resp = cognito.list_users(
            UserPoolId=user_pool_id,
            Filter=f'email = "{email.lower()}"',
            Limit=1
        )
        users = resp.get("Users", [])
        username = users[0]["Username"] if users else None
        return username
    except Exception as e:
        raise


def get_cognito_groups(user_pool_id: str, username: str) -> List[str]:
    groups = []
    try:
        paginator = cognito.get_paginator("admin_list_groups_for_user")
        for page in paginator.paginate(UserPoolId=user_pool_id, Username=username):
            groups.extend(g["GroupName"] for g in page.get("Groups", []))
        return groups
    except Exception as e:
        raise


def set_cognito_role(user_pool_id: str, username: str, target: Role) -> Tuple[List[str], List[str], bool]:
    """
    Aplica el rol objetivo en Cognito:
    - añade target si falta
    - quita el otro si existe
    Devuelve (before_groups, after_groups, changed)
    """
    before = get_cognito_groups(user_pool_id, username)
    desired = target
    undesired = "Supervisor" if target == "Agent" else "Agent"

    changed = False
    try:
        if desired not in before:
            cognito.admin_add_user_to_group(UserPoolId=user_pool_id, Username=username, GroupName=desired)
            changed = True
        if undesired in before:
            cognito.admin_remove_user_from_group(UserPoolId=user_pool_id, Username=username, GroupName=undesired)
            changed = True
    except ClientError as e:
        msg = e.response.get("Error", {}).get("Message", str(e))
        raise RuntimeError(f"Cognito sync error: {msg}")

    after = get_cognito_groups(user_pool_id, username)
    return before, after, changed


def global_sign_out(user_pool_id: str, username: str) -> None:
    # Invalida refresh tokens; los ID/Access actuales expirarán solos.
    try:
        cognito.admin_user_global_sign_out(UserPoolId=user_pool_id, Username=username)
    except Exception as e:
        raise


def disable_cognito_user(user_pool_id: str, username: str) -> None:
    """
    Deshabilita un usuario en Cognito.
    Un usuario deshabilitado no puede iniciar sesión.
    """
    try:
        cognito.admin_disable_user(UserPoolId=user_pool_id, Username=username)
    except ClientError as e:
        error_msg = e.response.get("Error", {}).get("Message", str(e))
        raise RuntimeError(f"Error deshabilitando usuario en Cognito: {error_msg}")
    except Exception as e:
        raise


def enable_cognito_user(user_pool_id: str, username: str) -> None:
    """
    Habilita un usuario en Cognito.
    Un usuario habilitado puede iniciar sesión.
    """
    try:
        cognito.admin_enable_user(UserPoolId=user_pool_id, Username=username)
    except ClientError as e:
        error_msg = e.response.get("Error", {}).get("Message", str(e))
        raise RuntimeError(f"Error habilitando usuario en Cognito: {error_msg}")
    except Exception as e:
        raise

