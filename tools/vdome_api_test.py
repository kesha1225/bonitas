from __future__ import annotations

import argparse
import json
import os
import sys
import textwrap
import uuid
from datetime import datetime
from typing import Any

import requests


DEFAULT_RESIDENT_URL = "https://resident-rest.vdome.mts.ru"
DEFAULT_GATEWAY_URL = "https://gateway.vdome.mts.ru"
DEFAULT_DEVICE_TYPE = "ANDROID"
DEFAULT_USER_AGENT = "okhttp/4.12.0"


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _redact(value: str) -> str:
    if not value:
        return value
    if len(value) <= 4:
        return "****"
    return value[:2] + "***" + value[-2:]


def _redact_headers(headers: dict[str, str]) -> dict[str, str]:
    redacted = {}
    for key, value in headers.items():
        lower = key.lower()
        if lower in {"authorization", "x-auth-token", "x-device-token"}:
            redacted[key] = _redact(value)
        else:
            redacted[key] = value
    return redacted


def _redact_body(body: Any) -> Any:
    if isinstance(body, dict):
        masked = {}
        for key, value in body.items():
            if key.lower() in {"phone", "code", "refreshtoken"}:
                masked[key] = _redact(str(value))
            else:
                masked[key] = value
        return masked
    return body


def _format_json(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, indent=2)
    except Exception:
        return str(value)


def _normalize_phone(phone: str, mode: str) -> str:
    if mode == "raw":
        return phone
    digits = "".join(ch for ch in phone if ch.isdigit())
    if mode == "digits10":
        if len(digits) == 11 and digits[0] in {"7", "8"}:
            digits = digits[1:]
        return digits
    return phone


class ApiTester:
    def __init__(
        self,
        resident_url: str,
        gateway_url: str,
        device_type: str,
        device_token: str | None,
        user_agent: str,
        accept: str,
        timeout: float,
        log_file: str | None,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        self.resident_url = resident_url.rstrip("/")
        self.gateway_url = gateway_url.rstrip("/")
        self.device_type = device_type
        self.device_token = device_token
        self.user_agent = user_agent
        self.accept = accept
        self.timeout = timeout
        self.log_file = log_file
        self.extra_headers = extra_headers or {}
        self.session = requests.Session()

    def _log(self, text: str) -> None:
        line = f"[{_now()}] {text}"
        print(line)
        if self.log_file:
            with open(self.log_file, "a", encoding="utf-8") as handle:
                handle.write(line + "\n")

    def request(
        self,
        method: str,
        url: str,
        *,
        access_token: str | None = None,
        headers: dict[str, str] | None = None,
        json_body: Any | None = None,
        params: dict[str, Any] | None = None,
    ) -> requests.Response:
        request_id = str(uuid.uuid4())
        base_headers = {
            "X-Device-Type": self.device_type,
            "Request-Id": request_id,
            "User-Agent": self.user_agent,
            "Accept": self.accept,
        }
        if self.device_token:
            base_headers["X-Device-Token"] = self.device_token
        if access_token:
            base_headers["Authorization"] = f"Bearer {access_token}"
            base_headers["X-Auth-Token"] = access_token
        if headers:
            base_headers.update(headers)
        if self.extra_headers:
            base_headers.update(self.extra_headers)

        self._log(f"REQUEST {method} {url}")
        self._log(f"Request-Id: {request_id}")
        self._log(f"Headers: {_format_json(_redact_headers(base_headers))}")
        if json_body is not None:
            self._log(f"JSON: {_format_json(_redact_body(json_body))}")

        response = self.session.request(
            method,
            url,
            headers=base_headers,
            json=json_body,
            params=params,
            timeout=self.timeout,
        )

        self._log(f"RESPONSE {response.status_code}")
        content_type = response.headers.get("Content-Type", "")
        self._log(f"Content-Type: {content_type}")
        self._log(f"Response-Headers: {_format_json(dict(response.headers))}")
        body_text = response.text
        if len(body_text) > 4000:
            body_text = body_text[:4000] + "...<truncated>"
        self._log(f"Body: {body_text}")
        return response

    def auth_init(self, phone: str, url_override: str | None = None) -> requests.Response:
        base_url = (url_override or self.resident_url).rstrip("/")
        return self.request(
            "POST",
            f"{base_url}/user-service/api/v2/auth/init",
            json_body={"phone": phone},
        )

    def auth_login(self, phone: str, code: str, url_override: str | None = None) -> requests.Response:
        base_url = (url_override or self.resident_url).rstrip("/")
        return self.request(
            "POST",
            f"{base_url}/user-service/api/v2/auth/login",
            json_body={"phone": phone, "code": code},
        )

    def auth_refresh(self, refresh_token: str, url_override: str | None = None) -> requests.Response:
        base_url = (url_override or self.resident_url).rstrip("/")
        return self.request(
            "PUT",
            f"{base_url}/user-service/api/v2/auth/refresh",
            json_body={"refreshToken": refresh_token},
        )

    def cameras(self, access_token: str, limit: int) -> requests.Response:
        return self.request(
            "GET",
            f"{self.gateway_url}/domofon/api/intercom/v1/cameras",
            access_token=access_token,
            params={"limit": limit},
        )


def _parse_args() -> argparse.Namespace:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--resident-url",
        default=os.getenv("VDOME_RESIDENT_URL", DEFAULT_RESIDENT_URL),
    )
    common.add_argument(
        "--gateway-url",
        default=os.getenv("VDOME_GATEWAY_URL", DEFAULT_GATEWAY_URL),
    )
    common.add_argument(
        "--device-type",
        default=os.getenv("VDOME_DEVICE_TYPE", DEFAULT_DEVICE_TYPE),
    )
    common.add_argument(
        "--user-agent",
        default=os.getenv("VDOME_USER_AGENT", DEFAULT_USER_AGENT),
    )
    common.add_argument(
        "--accept",
        default=os.getenv("VDOME_ACCEPT", "application/json"),
    )
    common.add_argument(
        "--device-token",
        default=os.getenv("VDOME_DEVICE_TOKEN"),
    )
    common.add_argument("--timeout", type=float, default=20.0)
    common.add_argument("--log-file", default=None)
    common.add_argument(
        "--phone-mode",
        choices=["raw", "digits10"],
        default=os.getenv("VDOME_PHONE_MODE", "raw"),
        help="raw = send as-is, digits10 = keep only digits and drop leading 7/8",
    )
    common.add_argument(
        "--header",
        action="append",
        default=[],
        help="Extra header like 'Key: Value'. Can be repeated.",
    )

    parser = argparse.ArgumentParser(
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=textwrap.dedent(
            """
            Vdome API tester with verbose logs.

            Examples:
              python tools/vdome_api_test.py init --phone +7XXXXXXXXXX
              python tools/vdome_api_test.py login --phone +7XXXXXXXXXX --code 1234
              python tools/vdome_api_test.py cameras --access-token <token>
              python tools/vdome_api_test.py full --phone +7XXXXXXXXXX --code 1234
            """
        ).strip(),
        parents=[common],
    )

    sub = parser.add_subparsers(dest="command", required=True)

    init_cmd = sub.add_parser("init", parents=[common])
    init_cmd.add_argument("--phone", required=True)

    login_cmd = sub.add_parser("login", parents=[common])
    login_cmd.add_argument("--phone", required=True)
    login_cmd.add_argument("--code", required=True)

    refresh_cmd = sub.add_parser("refresh", parents=[common])
    refresh_cmd.add_argument("--refresh-token", required=True)

    cameras_cmd = sub.add_parser("cameras", parents=[common])
    cameras_cmd.add_argument("--access-token", required=True)
    cameras_cmd.add_argument("--limit", type=int, default=1000)

    full_cmd = sub.add_parser("full", parents=[common])
    full_cmd.add_argument("--phone", required=True)
    full_cmd.add_argument("--code")

    probe_cmd = sub.add_parser("probe-init", parents=[common])
    probe_cmd.add_argument("--phone", required=True)
    probe_cmd.add_argument(
        "--probe-host",
        action="append",
        default=[],
        help="Additional base URL to probe (can be repeated).",
    )
    probe_cmd.add_argument(
        "--no-stop-on-success",
        action="store_true",
        help="Do not stop after the first non-4xx response.",
    )

    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    extra_headers: dict[str, str] = {}
    for item in args.header:
        if ":" not in item:
            print(f"Invalid header format: {item}. Use 'Key: Value'.", file=sys.stderr)
            return 2
        key, value = item.split(":", 1)
        extra_headers[key.strip()] = value.strip()

    tester = ApiTester(
        resident_url=args.resident_url,
        gateway_url=args.gateway_url,
        device_type=args.device_type,
        device_token=args.device_token,
        user_agent=args.user_agent,
        accept=args.accept,
        timeout=args.timeout,
        log_file=args.log_file,
        extra_headers=extra_headers,
    )

    if args.command == "init":
        phone = _normalize_phone(args.phone, args.phone_mode)
        tester.auth_init(phone)
        return 0

    if args.command == "login":
        phone = _normalize_phone(args.phone, args.phone_mode)
        tester.auth_login(phone, args.code)
        return 0

    if args.command == "refresh":
        tester.auth_refresh(args.refresh_token)
        return 0

    if args.command == "cameras":
        tester.cameras(args.access_token, args.limit)
        return 0

    if args.command == "full":
        phone = _normalize_phone(args.phone, args.phone_mode)
        tester.auth_init(phone)
        code = args.code
        if not code:
            code = input("SMS code: ").strip()
        login_response = tester.auth_login(phone, code)
        try:
            payload = login_response.json()
        except Exception:
            tester._log("Failed to parse login response JSON")
            return 1

        result = payload.get("result") if isinstance(payload, dict) else None
        if not result and isinstance(payload, dict) and "accessToken" in payload:
            result = payload
        access_token = None
        if isinstance(result, dict):
            access_token = result.get("accessToken")
        if not access_token:
            tester._log("No access token found in login response")
            return 1

        tester.cameras(access_token, 1000)
        return 0

    if args.command == "probe-init":
        phone = _normalize_phone(args.phone, args.phone_mode)
        extra_hosts = [
            "https://freecom-app.mts.ru",
            "https://kolya.site-stage.freecom-app-test.mts.ru",
        ]
        for item in args.probe_host:
            if item:
                extra_hosts.append(item)
        targets = [
            ("resident", tester.resident_url),
            ("gateway", tester.gateway_url),
        ] + [(f"extra-{idx + 1}", host) for idx, host in enumerate(extra_hosts)]
        seen_targets = []
        for label, base in targets:
            base_clean = base.rstrip("/")
            if base_clean in seen_targets:
                continue
            seen_targets.append(base_clean)
        targets = [(f"host-{idx + 1}", base) for idx, base in enumerate(seen_targets)]
        paths = [
            "/user-service/api/v2/auth/init",
            "/api/v2/auth/init",
            "/user-service/v2/api/auth/init",
        ]
        stop_on_success = not args.no_stop_on_success
        for label, base in targets:
            for path in paths:
                tester._log(f"PROBE {label} {path}")
                response = tester.request(
                    "POST",
                    f"{base}{path}",
                    json_body={"phone": phone},
                )
                if stop_on_success and response.status_code < 400:
                    tester._log(f"PROBE success on {base}{path}")
                    return 0
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
