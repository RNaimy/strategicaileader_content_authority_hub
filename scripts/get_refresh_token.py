import os
import sys
from google_auth_oauthlib.flow import InstalledAppFlow


def get_env_var(name):
    value = os.getenv(name)
    if not value:
        print(f"Error: Environment variable {name} not set.")
        sys.exit(1)
    return value


def build_client_config(client_id, client_secret):
    return {
        "installed": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    }


def get_refresh_token(client_id, client_secret, scopes, api_name):
    config = build_client_config(client_id, client_secret)
    flow = InstalledAppFlow.from_client_config(config, scopes=scopes)
    creds = flow.run_local_server(port=0)
    if not creds.refresh_token:
        print(
            "No refresh token received. Try removing previous tokens or using a different Google account."
        )
        sys.exit(1)
    print(f"\n=== {api_name} OAuth Success ===")
    print("Your refresh token is:\n")
    print(creds.refresh_token)
    print(
        f"\nCopy the above refresh token and paste it into your .env file as the value for {api_name.upper()}_REFRESH_TOKEN\n"
    )


def main():
    print("Which API do you want a refresh token for?")
    print("1. GA4 (Google Analytics Data API)")
    print("2. GSC (Search Console API)")
    choice = input("Enter 1 or 2: ").strip()
    if choice == "1":
        client_id = get_env_var("GA4_CLIENT_ID")
        client_secret = get_env_var("GA4_CLIENT_SECRET")
        scopes = ["https://www.googleapis.com/auth/analytics.readonly"]
        api_name = "GA4"
    elif choice == "2":
        client_id = get_env_var("GSC_CLIENT_ID")
        client_secret = get_env_var("GSC_CLIENT_SECRET")
        scopes = ["https://www.googleapis.com/auth/webmasters.readonly"]
        api_name = "GSC"
    else:
        print("Invalid choice. Exiting.")
        sys.exit(1)
    get_refresh_token(client_id, client_secret, scopes, api_name)


if __name__ == "__main__":
    main()
