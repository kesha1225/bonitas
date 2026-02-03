from __future__ import annotations

import os
import secrets
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, IO, Optional
from fastapi import Depends, FastAPI, Form, HTTPException, Request, Response, status
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from dotenv import load_dotenv

from vdome_api import VdomeApiError, VdomeClient, WatchTokenError, decode_watch_token, pick_rtsp_url

load_dotenv()
STREAM_USERNAME = os.getenv("VDOME_STREAM_USER")
STREAM_PASSWORD = os.getenv("VDOME_STREAM_PASSWORD")
OPEN_CODE = (os.getenv("VDOME_OPEN_CODE") or "").strip() or None
INTERCOM_ID = (os.getenv("VDOME_INTERCOM_ID") or "").strip() or None
INTERCOM_LOCK = (os.getenv("VDOME_INTERCOM_LOCK") or "").strip() or None

ACCESS_TOKEN = os.getenv("VDOME_ACCESS_TOKEN", "")
REFRESH_TOKEN = os.getenv("VDOME_REFRESH_TOKEN", "")
DEVICE_TOKEN = os.getenv("VDOME_DEVICE_TOKEN")

STREAM_CAMERA_ID = os.getenv("VDOME_STREAM_CAMERA_ID")
STREAM_CAMERA_NAME = os.getenv("VDOME_STREAM_CAMERA_NAME")


app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

security = HTTPBasic(auto_error=False)

client = VdomeClient(device_token=DEVICE_TOKEN)


@dataclass
class TokenState:
    access_token: str
    refresh_token: str


TOKEN_STATE = TokenState(access_token=ACCESS_TOKEN, refresh_token=REFRESH_TOKEN)


@dataclass
class HlsStream:
    process: subprocess.Popen
    directory: Path
    rtsp_url: str
    started_at: float
    log_path: Path
    log_file: Optional[IO[str]] = None


HLS_STREAMS: Dict[str, HlsStream] = {}
HLS_ROOT = Path("/tmp/vdome_hls")

CAMERA_CACHE: Dict[str, dict] = {}
CAMERA_ORDER: list[str] = []
CAMERA_CACHE_AT = 0.0
CAMERA_CACHE_TTL = 30.0

INTERCOM_CACHE: list[dict] = []
INTERCOM_CACHE_AT = 0.0
INTERCOM_CACHE_TTL = 30.0


class ConfigError(RuntimeError):
    pass


def _basic_challenge(realm: str) -> Dict[str, str]:
    return {"WWW-Authenticate": f'Basic realm="{realm}", charset="UTF-8"'}


def _require_credentials(
    credentials: Optional[HTTPBasicCredentials],
    username: Optional[str],
    password: Optional[str],
    realm: str,
) -> None:
    if not username or not password:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Server auth is not configured",
        )
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers=_basic_challenge(realm),
        )
    user_ok = secrets.compare_digest(credentials.username, username)
    pass_ok = secrets.compare_digest(credentials.password, password)
    if not (user_ok and pass_ok):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers=_basic_challenge(realm),
        )


def require_stream_auth(credentials: Optional[HTTPBasicCredentials] = Depends(security)) -> None:
    _require_credentials(credentials, STREAM_USERNAME, STREAM_PASSWORD, "VDome Stream")


def _camera_key(camera: dict, index: int) -> str:
    for key in ("serverId", "id", "cameraId"):
        value = camera.get(key)
        if value:
            return str(value)
    return f"idx-{index}"


def _ensure_hls_stream(camera_id: str, rtsp_url: str) -> Optional[Path]:
    if not shutil.which("ffmpeg"):
        return None

    stream_key = camera_id
    existing = HLS_STREAMS.get(stream_key)
    if existing and existing.process.poll() is None:
        return existing.directory

    stream_dir = HLS_ROOT / stream_key
    stream_dir.mkdir(parents=True, exist_ok=True)

    manifest_path = stream_dir / "index.m3u8"
    segment_pattern = str(stream_dir / "seg_%03d.ts")
    log_path = stream_dir / "ffmpeg.log"

    cmd = [
        "ffmpeg",
        "-rtsp_transport",
        "tcp",
        "-i",
        rtsp_url,
        "-c:v",
        "copy",
        "-c:a",
        "aac",
        "-b:a",
        "96k",
        "-f",
        "hls",
        "-hls_time",
        "2",
        "-hls_list_size",
        "6",
        "-hls_flags",
        "delete_segments+append_list",
        "-hls_segment_filename",
        segment_pattern,
        str(manifest_path),
    ]
    log_file = log_path.open("a", encoding="utf-8")
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=log_file,
    )
    HLS_STREAMS[stream_key] = HlsStream(
        process=process,
        directory=stream_dir,
        rtsp_url=rtsp_url,
        started_at=time.time(),
        log_path=log_path,
        log_file=log_file,
    )
    time.sleep(0.2)
    if process.poll() is not None:
        return None
    return stream_dir


def _require_access_token() -> str:
    if not TOKEN_STATE.access_token:
        raise ConfigError("VDOME_ACCESS_TOKEN is not set")
    return TOKEN_STATE.access_token


def _api_call(fn):
    access_token = _require_access_token()
    try:
        return fn(access_token)
    except VdomeApiError as exc:
        if exc.status_code == 401 and TOKEN_STATE.refresh_token:
            new_access = client.auth_refresh(TOKEN_STATE.refresh_token)
            TOKEN_STATE.access_token = new_access
            return fn(new_access)
        raise


def _refresh_camera_cache(force: bool = False) -> Dict[str, dict]:
    global CAMERA_CACHE, CAMERA_ORDER, CAMERA_CACHE_AT
    now = time.time()
    if not force and CAMERA_CACHE and (now - CAMERA_CACHE_AT) < CAMERA_CACHE_TTL:
        return CAMERA_CACHE

    cameras_data = _api_call(lambda token: client.get_cameras(token))
    if not isinstance(cameras_data, list):
        cameras_data = []

    CAMERA_CACHE = {}
    CAMERA_ORDER = []
    for idx, camera in enumerate(cameras_data):
        key = _camera_key(camera, idx)
        CAMERA_CACHE[key] = camera
        CAMERA_ORDER.append(key)

    CAMERA_CACHE_AT = now
    return CAMERA_CACHE


def _refresh_intercom_cache(force: bool = False) -> list[dict]:
    global INTERCOM_CACHE, INTERCOM_CACHE_AT
    now = time.time()
    if not force and INTERCOM_CACHE and (now - INTERCOM_CACHE_AT) < INTERCOM_CACHE_TTL:
        return INTERCOM_CACHE

    intercoms_data = _api_call(lambda token: client.get_intercoms(token))
    if not isinstance(intercoms_data, list):
        intercoms_data = []

    INTERCOM_CACHE = intercoms_data
    INTERCOM_CACHE_AT = now
    return INTERCOM_CACHE


def _normalize_id(value: Optional[object]) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _match_intercom_id(intercoms: list[dict], target: Optional[str]) -> Optional[dict]:
    if not target:
        return None
    for intercom in intercoms:
        intercom_id = _normalize_id(intercom.get("id") or intercom.get("intercomId"))
        if intercom_id == target:
            return intercom
    return None


def _select_intercom(camera: dict, intercoms: list[dict]) -> Optional[dict]:
    if not intercoms:
        return None

    if INTERCOM_ID:
        forced = _match_intercom_id(intercoms, _normalize_id(INTERCOM_ID))
        if forced:
            return forced

    camera_parent = _normalize_id(camera.get("parent") or camera.get("parentId"))
    if camera_parent:
        matched = _match_intercom_id(intercoms, camera_parent)
        if matched:
            return matched

    camera_ids = {
        _normalize_id(camera.get("serverId")),
        _normalize_id(camera.get("id")),
        _normalize_id(camera.get("cameraId")),
    }
    for intercom in intercoms:
        intercom_camera = intercom.get("camera") or {}
        intercom_camera_id = _normalize_id(intercom_camera.get("id"))
        if intercom_camera_id and intercom_camera_id in camera_ids:
            return intercom

    camera_name = camera.get("name")
    if isinstance(camera_name, str):
        target = camera_name.strip().lower()
        for intercom in intercoms:
            name = intercom.get("name")
            if isinstance(name, str) and name.strip().lower() == target:
                return intercom

    return intercoms[0]


def _get_camera(camera_id: str) -> Optional[dict]:
    cameras = _refresh_camera_cache()
    camera = cameras.get(camera_id)
    if camera:
        return camera
    cameras = _refresh_camera_cache(force=True)
    return cameras.get(camera_id)


def _select_camera_id(
    cameras: Dict[str, dict],
    preferred_id: Optional[str],
    preferred_name: Optional[str],
) -> Optional[str]:
    if preferred_id:
        preferred_id = preferred_id.strip()
        if preferred_id in cameras:
            return preferred_id
        for key, camera in cameras.items():
            for field in ("serverId", "id", "cameraId"):
                value = camera.get(field)
                if value is not None and str(value) == preferred_id:
                    return key
    if preferred_name:
        target = preferred_name.strip().lower()
        for key, camera in cameras.items():
            name = camera.get("name")
            if isinstance(name, str) and name.lower() == target:
                return key
    if CAMERA_ORDER:
        return CAMERA_ORDER[0]
    return None


def _json_result(message: str, ok: bool, status_code: int = status.HTTP_200_OK) -> JSONResponse:
    return JSONResponse({"ok": ok, "message": message}, status_code=status_code)


@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    return RedirectResponse("/stream", status_code=status.HTTP_302_FOUND)


@app.get("/stream", response_class=HTMLResponse)
def stream(
    request: Request,
    camera_id: Optional[str] = None,
    info: Optional[str] = None,
    _: None = Depends(require_stream_auth),
) -> HTMLResponse:
    try:
        cameras = _refresh_camera_cache()
    except (ConfigError, VdomeApiError) as exc:
        return templates.TemplateResponse(
            "stream.html",
            {
                "request": request,
                "title": "Stream",
                "error": str(exc),
            },
        )

    if not cameras:
        return templates.TemplateResponse(
            "stream.html",
            {
                "request": request,
                "title": "Stream",
                "error": "No cameras available",
            },
        )

    selected_id = _select_camera_id(cameras, camera_id or STREAM_CAMERA_ID, STREAM_CAMERA_NAME)
    if not selected_id:
        return templates.TemplateResponse(
            "stream.html",
            {
                "request": request,
                "title": "Stream",
                "error": "Camera not found",
            },
        )

    camera = cameras.get(selected_id)
    if not camera:
        return templates.TemplateResponse(
            "stream.html",
            {
                "request": request,
                "title": "Stream",
                "error": "Camera not found",
            },
        )

    name = camera.get("name") or f"Camera {selected_id}"
    rtsp_url = pick_rtsp_url(camera)
    ffmpeg_available = shutil.which("ffmpeg") is not None
    stream_dir = None
    if rtsp_url and ffmpeg_available:
        stream_dir = _ensure_hls_stream(selected_id, rtsp_url)

    has_preview = bool(camera.get("watch_token") or camera.get("watchToken"))
    preview_url = f"/preview/{selected_id}?t={int(time.time())}" if has_preview else ""
    use_hls = stream_dir is not None

    fallback_reason = "RTSP not available for this camera."
    if not rtsp_url:
        fallback_reason = "RTSP not available for this camera."
    elif not ffmpeg_available:
        fallback_reason = "ffmpeg is not installed."
    elif not has_preview:
        fallback_reason = "Preview token not available for this camera."

    open_disabled_reason = None
    intercom_id = None
    intercom_name = None
    lock_items: list[dict] = []
    lock_number: Optional[int] = None

    if not OPEN_CODE:
        open_disabled_reason = "Open code is not configured."
    elif not (OPEN_CODE.isdigit() and len(OPEN_CODE) == 4):
        open_disabled_reason = "Open code must be exactly 4 digits."
    else:
        try:
            intercoms = _refresh_intercom_cache()
        except (ConfigError, VdomeApiError) as exc:
            open_disabled_reason = f"Intercom error: {exc}"
            intercoms = []

        intercom = _select_intercom(camera, intercoms) if intercoms else None
        if not intercom:
            open_disabled_reason = "Intercom not found. Set VDOME_INTERCOM_ID."
        else:
            intercom_id = _normalize_id(intercom.get("id") or intercom.get("intercomId"))
            intercom_name = intercom.get("name") or (f"Intercom {intercom_id}" if intercom_id else None)
            if intercom.get("canUnlock") is False:
                open_disabled_reason = "Unlock disabled for this intercom."
            locks = intercom.get("locks") or {}
            for lock in locks.get("items") or []:
                number = lock.get("number")
                if number is None:
                    continue
                label = lock.get("name") or f"Lock {number}"
                lock_items.append({"number": number, "label": label})

            if INTERCOM_LOCK:
                try:
                    lock_number = int(INTERCOM_LOCK)
                except ValueError:
                    open_disabled_reason = "VDOME_INTERCOM_LOCK must be numeric."
            elif len(lock_items) == 1:
                lock_number = lock_items[0]["number"]

    return templates.TemplateResponse(
        "stream.html",
        {
            "request": request,
            "title": name,
            "name": name,
            "camera_id": selected_id,
            "preview_url": preview_url,
            "use_hls": use_hls,
            "hls_manifest": f"/hls/{selected_id}/index.m3u8",
            "fallback_reason": fallback_reason,
            "rtsp_url": rtsp_url,
            "info": info,
            "open_disabled_reason": open_disabled_reason,
            "intercom_id": intercom_id,
            "intercom_name": intercom_name,
            "lock_items": lock_items,
            "lock_number": lock_number,
        },
    )


@app.get("/preview/{camera_id}")
def preview(camera_id: str, _: None = Depends(require_stream_auth)) -> Response:
    try:
        camera = _get_camera(camera_id)
    except (ConfigError, VdomeApiError) as exc:
        return PlainTextResponse(str(exc), status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)

    if not camera:
        return PlainTextResponse("Camera not found", status_code=status.HTTP_404_NOT_FOUND)

    watch_token = camera.get("watch_token") or camera.get("watchToken")
    if not watch_token:
        return PlainTextResponse("Preview not available", status_code=status.HTTP_404_NOT_FOUND)

    try:
        token_data = decode_watch_token(watch_token)
    except WatchTokenError:
        return PlainTextResponse("Invalid watch token", status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)

    if not token_data.api or token_data.camid is None:
        return PlainTextResponse("Preview not available", status_code=status.HTTP_404_NOT_FOUND)

    try:
        image = client.get_preview_image(watch_token, token_data.api, token_data.camid)
    except Exception:
        _refresh_camera_cache(force=True)
        camera = _get_camera(camera_id)
        watch_token = (camera.get("watch_token") or camera.get("watchToken")) if camera else None
        if not watch_token:
            return PlainTextResponse("Failed to load preview", status_code=status.HTTP_502_BAD_GATEWAY)
        try:
            token_data = decode_watch_token(watch_token)
            if not token_data.api or token_data.camid is None:
                return PlainTextResponse("Preview not available", status_code=status.HTTP_404_NOT_FOUND)
            image = client.get_preview_image(watch_token, token_data.api, token_data.camid)
        except Exception:
            return PlainTextResponse("Failed to load preview", status_code=status.HTTP_502_BAD_GATEWAY)

    return Response(content=image, media_type="image/jpeg")


@app.get("/hls/{camera_id}/{filename}")
def hls_file(camera_id: str, filename: str, _: None = Depends(require_stream_auth)) -> Response:
    stream = HLS_STREAMS.get(camera_id)
    if not stream:
        return PlainTextResponse("Stream not found", status_code=status.HTTP_404_NOT_FOUND)

    target = (stream.directory / filename).resolve()
    if not str(target).startswith(str(stream.directory.resolve())):
        return PlainTextResponse("Invalid path", status_code=status.HTTP_400_BAD_REQUEST)

    if not target.exists():
        return PlainTextResponse("Not ready", status_code=status.HTTP_404_NOT_FOUND)

    return FileResponse(target)


@app.post("/open")
def open_intercom(
    intercom_id: str = Form(...),
    code: str = Form(...),
    lock_number: Optional[str] = Form(None),
    _: None = Depends(require_stream_auth),
) -> JSONResponse:
    intercom_id = intercom_id.strip()
    if not intercom_id:
        return _json_result("Intercom ID is missing", ok=False, status_code=status.HTTP_400_BAD_REQUEST)
    if not OPEN_CODE:
        return _json_result("Open code is not configured", ok=False, status_code=status.HTTP_400_BAD_REQUEST)
    if not (code.isdigit() and len(code) == 4):
        return _json_result("Code must be exactly 4 digits", ok=False, status_code=status.HTTP_400_BAD_REQUEST)
    if not secrets.compare_digest(code, OPEN_CODE):
        return _json_result("Invalid code", ok=False, status_code=status.HTTP_401_UNAUTHORIZED)

    lock_value: Optional[int] = None
    if lock_number:
        try:
            lock_value = int(lock_number)
        except ValueError:
            return _json_result("Invalid lock number", ok=False, status_code=status.HTTP_400_BAD_REQUEST)

    try:
        _api_call(lambda token: client.open_intercom(token, intercom_id, lock_value))
    except (ConfigError, VdomeApiError) as exc:
        return _json_result(f"Open failed: {exc}", ok=False, status_code=status.HTTP_502_BAD_GATEWAY)

    return _json_result("Open command sent", ok=True)
