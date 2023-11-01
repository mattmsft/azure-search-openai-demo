import asyncio
import os

from azure.identity.aio import AzureDeveloperCliCredential

from auth_common import (
    get_application,
    get_auth_headers,
    test_authentication_enabled,
    update_application,
)


async def main():
    if not test_authentication_enabled():
        print("Not updating authentication...")
        exit(0)

    print("Updating authentication...")
    credential = AzureDeveloperCliCredential()
    auth_headers = await get_auth_headers(credential)

    uri = os.getenv("BACKEND_URI")
    client_app_id = os.getenv("AZURE_CLIENT_APP_ID")
    client_object_id = await get_application(auth_headers, client_app_id)
    # Redirect URIs need to be relative to the deployed application
    payload = {
        "publicClient": {"redirectUris": []},
        "spa": {
            "redirectUris": [
                "http://localhost:50505/redirect",
                f"{uri}/redirect",
            ]
        },
        "web": {
            "redirectUris": [
                f"{uri}/.auth/login/aad/callback",
            ]
        },
    }
    await update_application(auth_headers, client_object_id, payload)


if __name__ == "__main__":
    asyncio.run(main())