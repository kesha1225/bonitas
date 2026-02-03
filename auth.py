#!/usr/bin/env python3
"""Quick auth script - pass callback URL as first argument."""

import sys
from vdome_api import VdomeClient

if len(sys.argv) < 2:
    client = VdomeClient()
    print(client.get_oauth_authorize_url())
    print("\nUsage: uv run python auth.py 'CALLBACK_URL'")
    sys.exit(0)

client = VdomeClient()
try:
    arg = sys.argv[1]
    if arg.lstrip().startswith("{"):
        tokens = client.tokens_from_callback_payload(arg)
    else:
        tokens = client.exchange_oauth_code(arg)
    print(f"ACCESS={tokens.access_token}")
    print(f"REFRESH={tokens.refresh_token}")

    # Test cameras
    cameras = client.get_cameras(tokens.access_token)
    print(f"\nCameras: {len(cameras)}")
    for c in cameras[:5]:
        print(f"  {c.get('name')}: {c.get('id')}")
except Exception as e:
    print(f"Error: {e}")
    if hasattr(e, 'response_data'):
        print(e.response_data)
