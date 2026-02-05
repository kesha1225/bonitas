from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse, urlunparse


@dataclass
class TokenData:
    camid: int | None
    token: str | None
    api: str | None


class WatchTokenError(ValueError):
    pass


def _b64decode_padded(data: str) -> bytes:
    data = data.strip()
    pad = "=" * (-len(data) % 4)
    return base64.b64decode(data + pad)


def decode_watch_token(watch_token: str) -> TokenData:
    if not watch_token:
        raise WatchTokenError("Empty watch_token")
    try:
        raw = _b64decode_padded(watch_token)
        payload = json.loads(raw.decode("utf-8"))
    except Exception as exc:
        raise WatchTokenError("Invalid watch_token") from exc

    camid = payload.get("camid")
    try:
        camid = int(camid) if camid is not None else None
    except Exception:
        camid = None

    return TokenData(camid=camid, token=payload.get("token"), api=payload.get("api"))


def build_preview_url(token_data: TokenData) -> str | None:
    if not token_data.api or token_data.camid is None:
        return None
    return f"https://{token_data.api}/api/v2/cameras/{token_data.camid}/preview/"


def inject_rtsp_auth(rtsp_url: str, login: str | None, password: str | None) -> str:
    if not login or not password:
        return rtsp_url
    parsed = urlparse(rtsp_url)
    if parsed.scheme.lower() != "rtsp":
        return rtsp_url
    if "@" in parsed.netloc:
        return rtsp_url
    netloc = f"{login}:{password}@{parsed.netloc}"
    return urlunparse((parsed.scheme, netloc, parsed.path, parsed.params, parsed.query, parsed.fragment))


def pick_rtsp_url(camera: dict[str, Any]) -> str | None:
    if not isinstance(camera, dict):
        return None

    rtsp = camera.get("rtsp") or camera.get("rtspUrl")
    if not rtsp:
        streams = camera.get("streams") or {}
        rtsp = streams.get("rtsp")

    if not rtsp:
        settings = camera.get("settings") or {}
        rtsp_settings = settings.get("rtsp") or {}
        stream = rtsp_settings.get("stream")
        if isinstance(stream, str) and stream.startswith("rtsp"):
            rtsp = stream

    if not rtsp:
        return None

    settings = camera.get("settings") or {}
    rtsp_settings = settings.get("rtsp") or {}
    auth = rtsp_settings.get("auth") or {}
    login = auth.get("login")
    password = auth.get("password")
    return inject_rtsp_auth(rtsp, login, password)
