#!/usr/bin/env python3
"""Test script for vdome API authentication via OAuth2."""

import sys
from vdome_api import VdomeClient

def main():
    client = VdomeClient()

    # Check if callback URL or JSON payload provided as argument
    if len(sys.argv) > 1:
        callback_arg = sys.argv[1]
        print("Using callback data from argument")
    else:
        print("=== VDome API OAuth2 Authentication ===\n")
        print("The API requires OAuth2 authentication through MTS SSO.\n")

        oauth_url = client.get_oauth_authorize_url()
        print("1. Open this URL in your browser:")
        print(f"\n   {oauth_url}\n")
        print("2. Login with your phone number and SMS code")
        print("3. After successful login, copy the callback URL")
        print("\n4. Run this script again with the URL as argument:")
        print(f"   uv run python test_auth.py 'CALLBACK_URL_HERE'\n")
        return

    print("\nExchanging code for tokens...")
    try:
        if callback_arg.lstrip().startswith("{"):
            tokens = client.tokens_from_callback_payload(callback_arg)
        else:
            tokens = client.exchange_oauth_code(callback_arg)
        print("Success!")
        print(f"Access token: {tokens.access_token[:50]}...")
        print(f"Refresh token: {tokens.refresh_token[:50]}...")
    except Exception as e:
        print(f"Error: {e}")
        if hasattr(e, 'response_data'):
            print(f"Response data: {e.response_data}")
        return

    print("\nTrying to get cameras...")
    try:
        cameras = client.get_cameras(tokens.access_token)
        print(f"Found {len(cameras)} cameras")
        for cam in cameras[:5]:
            print(f"  - {cam.get('name', 'Unknown')}: id={cam.get('id')}")
    except Exception as e:
        print(f"Error getting cameras: {e}")

    # Save tokens for later use
    print("\n--- Tokens saved to tokens.txt ---")
    with open("tokens.txt", "w") as f:
        f.write(f"access_token={tokens.access_token}\n")
        f.write(f"refresh_token={tokens.refresh_token}\n")


if __name__ == "__main__":
    main()
