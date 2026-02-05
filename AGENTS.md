# AGENTS.md

## Setup commands
- Install deps: `uv sync`
- Start demo server: `uvicorn demo_app:app --reload`
- Show API tester help: `python tools/vdome_api_test.py --help`

## Code style
- Python 3.13
- Keep changes small and explicit; prefer readable code over cleverness.
- Avoid non-ASCII unless the file already uses it.

## Dev environment tips
- Auth flow is phone + SMS code; there is no login/password.
- Phone must be sent as 10 digits (no `+7`). Use `--phone-mode digits10`.
- The API may require `X-Device-Token` (Firebase Installation ID).
- Preview images require `Authorization: Acc <watch_token>` header.

## Testing instructions
- There is no automated test suite.
- Use the CLI tester with logs:
  - `python tools/vdome_api_test.py init --phone 9000000000 --phone-mode digits10 --log-file /tmp/vdome_log.txt`
  - `python tools/vdome_api_test.py login --phone 9000000000 --code 0000 --phone-mode digits10 --log-file /tmp/vdome_log.txt`
  - `python tools/vdome_api_test.py cameras --access-token <token> --log-file /tmp/vdome_log.txt`
  - `python tools/vdome_api_test.py probe-init --phone 9000000000 --phone-mode digits10 --log-file /tmp/vdome_log.txt`
- Keep tokens and personal data redacted in shared logs.

## PR instructions
- If you change API behavior or CLI flags, update `README.md`.
- Do not commit secrets or personal data.
