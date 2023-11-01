import asyncio
import os
import subprocess
from typing import Dict, Tuple

import aiohttp
from azure.identity.aio import AzureDeveloperCliCredential

from auth_common import (
    TIMEOUT,
    get_application,
    get_auth_headers,
    test_authentication_enabled,
    update_application,
)


async def create_application(auth_headers: Dict[str, str], app_payload: object) -> Tuple[str, str]:
    async with aiohttp.ClientSession(headers=auth_headers, timeout=aiohttp.ClientTimeout(total=TIMEOUT)) as session:
        async with session.post("https://graph.microsoft.com/v1.0/applications", json=app_payload) as response:
            response_json = await response.json()
            object_id = response_json["id"]
            client_id = response_json["appId"]

    return object_id, client_id


async def add_client_secret(auth_headers: Dict[str, str], object_id: str):
    async with aiohttp.ClientSession(headers=auth_headers, timeout=aiohttp.ClientTimeout(total=TIMEOUT)) as session:
        async with session.post(
            f"https://graph.microsoft.com/v1.0/applications/{object_id}/addPassword",
            json={"passwordCredential": {"displayName": "secret"}},
        ) as response:
            response_json = await response.json()
            if response.status == 200:
                return response_json["secretText"]

            raise Exception(response_json)


async def create_or_update_application_with_secret(
    auth_headers: Dict[str, str], app_id_env_var: str, app_secret_env_var: str, app_payload: object
) -> Tuple[str, str, bool]:
    app_id = os.getenv(app_id_env_var, "no-id")
    created_app = False
    if app_id != "no-id":
        print(f"Checking if application {app_id} exists")
        object_id = await get_application(auth_headers, app_id)
        if object_id:
            print("Application already exists, not creating new one")
            await update_application(auth_headers, object_id, app_payload)
        else:
            print("Creating application registration")
            object_id, app_id = await create_application(auth_headers, app_payload)
            update_azd_env(app_id_env_var, app_id)
            created_app = True

    if os.getenv(app_secret_env_var, "no-secret") == "no-secret":
        print(f"Adding client secret to {app_id}")
        client_secret = await add_client_secret(auth_headers, object_id)
        update_azd_env(app_secret_env_var, client_secret)

    return (object_id, app_id, created_app)


def update_azd_env(name, val):
    subprocess.run(f"azd env set {name} {val}", shell=True)


def create_server_app_initial_payload():
    return {
        "displayName": "Azure Search OpenAI Demo Server App",
        "signInAudience": "AzureADandPersonalMicrosoftAccount",
    }


def create_server_app_permission_setup_payload(server_app_id: str):
    return {
        "api": {
            "knownClientApplications": [],
            "oauth2PermissionScopes": [
                {
                    "id": "7b207263-0c4a-4127-a6fe-38ea8c8cd1a7",
                    "adminConsentDisplayName": "Access Azure Search OpenAI Demo API",
                    "adminConsentDescription": "Allows the app to access Azure Search OpenAI Demo API as the signed-in user.",
                    "userConsentDisplayName": "Access Azure Search OpenAI Demo API",
                    "userConsentDescription": "Allow the app to access Azure Search OpenAI Demo API on your behalf",
                    "isEnabled": True,
                    "value": "access_as_user",
                    "type": "User",
                }
            ],
        },
        "requiredResourceAccess": [
            # Graph User.Read
            {
                "resourceAppId": "00000003-0000-0000-c000-000000000000",
                "resourceAccess": [{"id": "e1fe6dd8-ba31-4d61-89e7-88639da4683d", "type": "Scope"}],
            }
        ],
        "identifierUris": [f"api://{server_app_id}"],
    }


def create_client_app_payload(server_app_id: str, server_app_permission_setup_payload: object):
    return {
        "displayName": "Azure Search OpenAI Demo Client App",
        "signInAudience": "AzureADandPersonalMicrosoftAccount",
        "web": {
            "redirectUris": ["http://localhost:50505/.auth/login/aad/callback"],
            "implicitGrantSettings": {"enableIdTokenIssuance": True},
        },
        "spa": {"redirectUris": ["http://localhost:50505/redirect"]},
        "requiredResourceAccess": [
            # access_as_user from server app
            {
                "resourceAppId": server_app_id,
                "resourceAccess": [
                    {
                        "id": server_app_permission_setup_payload["api"]["oauth2PermissionScopes"][0]["id"],
                        "type": "Scope",
                    }
                ],
            },
            # Graph User.Read
            {
                "resourceAppId": "00000003-0000-0000-c000-000000000000",
                "resourceAccess": [{"id": "e1fe6dd8-ba31-4d61-89e7-88639da4683d", "type": "Scope"}],
            },
        ],
    }


def create_server_app_known_client_application_payload(client_app_id: str):
    return {
        "api": {
            "knownClientApplications": [client_app_id],
        }
    }


async def main():
    if not test_authentication_enabled():
        print("Not setting up authentication...")
        exit(0)

    print("Setting up authentication...")
    credential = AzureDeveloperCliCredential()
    auth_headers = await get_auth_headers(credential)

    server_object_id, server_app_id, _ = await create_or_update_application_with_secret(
        auth_headers,
        app_id_env_var="AZURE_SERVER_APP_ID",
        app_secret_env_var="AZURE_SERVER_APP_SECRET",
        app_payload=create_server_app_initial_payload(),
    )
    print("Setup server application permissions...")
    server_app_permission_payload = create_server_app_permission_setup_payload(server_app_id)
    await update_application(auth_headers, object_id=server_object_id, app_payload=server_app_permission_payload)
    _, client_app_id, _ = await create_or_update_application_with_secret(
        auth_headers,
        app_id_env_var="AZURE_CLIENT_APP_ID",
        app_secret_env_var="AZURE_CLIENT_APP_SECRET",
        app_payload=create_client_app_payload(server_app_id, server_app_permission_payload),
    )
    print("Setup server known client applications...")
    await update_application(
        auth_headers,
        object_id=server_object_id,
        app_payload=create_server_app_known_client_application_payload(client_app_id),
    )


if __name__ == "__main__":
    asyncio.run(main())