# Vdome API Reverse Engineering Plan

Goal: Build a reliable, reproducible understanding of the Vdome API (auth flow,
headers, endpoints, request/response formats) and validate it with tests.

Scope and constraints
- Use only your own account/data and permitted environments.
- Prefer static analysis first; use dynamic traffic capture when possible.
- Keep all findings timestamped and tied to APK version.

Phase 0: Inventory and baseline
- Record APK version, build flavor, split list, and source (store, archive, etc.).
- Note environment: host OS, emulator/device, network conditions.
- Create a working folder for extracted APK artifacts (do not overwrite originals).

Phase 1: Static analysis (APK)
- Decompile with jadx (or use existing decompile in vdome/).
- Identify base URLs and environments:
  - Search for BuildConfig, base URLs, and host constants.
  - Confirm resident and gateway base URLs.
- Enumerate endpoints:
  - Search for Retrofit interfaces in backend/api packages.
  - Extract method, path, and request models for each endpoint.
- Identify headers and auth:
  - Locate OkHttp interceptors and header constants.
  - Determine which clients add which headers.
  - Find auth, refresh, and token storage logic.
- Identify security controls:
  - Look for TLS pinning, integrity checks, root checks, or attestation usage.
  - Note libraries (OkHttp pinning, TrustManager overrides, SafetyNet, etc.).

Deliverable: Endpoint map (static)
- Table with columns: host, method, path, request model, response model, headers.
- Notes on auth/init/login/refresh, device token usage, and phone format.

Phase 2: Hypothesis of auth flow
- Draft expected flow based on static code:
  - auth/init -> SMS -> auth/login -> refresh -> authorized endpoints.
  - Alternative SMS flow (gw-intercom token endpoints) if present.
- List required headers per step and any device token dependencies.

Phase 3: Dynamic verification (preferred, requires internet)
- Use a device or emulator with working DNS.
- Configure capture:
  - Proxy (mitmproxy/Charles), install user CA on device.
  - Capture auth requests and responses during real login.
- If TLS pinning blocks capture:
  - Use Frida/objection to bypass pinning or patch APK.
  - Re-capture traffic and confirm real request formats.
- Save sanitized logs (redact phone/code/token) with timestamps.

Deliverable: Verified request/response samples
- Real, sanitized HTTP samples for each auth step.
- Confirmation of the exact headers and payload formats.

Phase 4: Reproduce with scripts
- Update tools/vdome_api_test.py and vdome_api client to match verified flow:
  - Correct paths, headers, and payloads.
  - Optional extra headers support for experiments.
- Add CLI helpers for DNS/headers/phone formatting.
- Add unit-style checks with canned sample responses.

Phase 5: End-to-end test
- Run login end-to-end with your number:
  - auth/init -> receive code -> auth/login -> refresh -> camera list.
- Validate that tokens work for authorized endpoints.
- Record outcomes and error codes.

Phase 6: Documentation
- Document the final flow, headers, and known gotchas.
- Note version dependencies and how to re-verify after app updates.

Success criteria
- Auth flow works reliably with your account.
- Headers and payloads are confirmed against live traffic.
- Scripts can reproduce the flow without manual tweaks.

