# Vdome API tools

Набор инструментов для работы с API Vdome: библиотека, CLI для получения токенов и демо-веб-панель. Веб-демо — страница `/stream` с просмотром камеры и кнопкой открытия двери по 4-значному коду. Поток идет через RTSP → HLS при наличии `ffmpeg`, иначе показывается превью.

## Что внутри

- Python-библиотека `vdome_api` для работы с API.
- CLI `tools/vdome_api_test.py` для авторизации и диагностики.
- Демо-панель на FastAPI для просмотра камеры и открытия двери.

## Быстрый старт

Установка:

```bash
python -m pip install -e .
```

Подготовьте переменные окружения:

```bash
cp .env.example .env
# заполните значения в .env
```

Запуск демо:

```bash
uvicorn demo_app:app --reload
```

Откройте `http://127.0.0.1:8000/stream` и введите Basic Auth логин/пароль.
Для реального доступа используйте HTTPS (например, через reverse proxy).

Обязательные переменные:
- `VDOME_ACCESS_TOKEN`
- `VDOME_OPEN_CODE`
- `VDOME_STREAM_USER`
- `VDOME_STREAM_PASSWORD`

Опциональные переменные:
- `VDOME_REFRESH_TOKEN` (для авто-рефреша)
- `VDOME_DEVICE_TOKEN` (Firebase Installation ID, если требуется)
- `VDOME_STREAM_CAMERA_ID` или `VDOME_STREAM_CAMERA_NAME` (если камер несколько)
- `VDOME_INTERCOM_ID` (если автосвязка не сработала)
- `VDOME_INTERCOM_LOCK` (номер замка)

## Использование библиотеки

```python
from vdome_api import VdomeClient

client = VdomeClient()
client.auth_init("9000000000")
# введите SMS код

tokens = client.auth_login("9000000000", "0000")

cameras = client.get_cameras(tokens.access_token)
print(cameras)
```

## Тестирование API через CLI

```bash
python tools/vdome_api_test.py init --phone 9000000000 --phone-mode digits10
python tools/vdome_api_test.py login --phone 9000000000 --code 0000 --phone-mode digits10
python tools/vdome_api_test.py cameras --access-token <token>
```

Для первичной диагностики хоста/пути:

```bash
python tools/vdome_api_test.py probe-init --phone 9000000000 --phone-mode digits10
```

Можно добавить дополнительные хосты:

```bash
python tools/vdome_api_test.py probe-init --phone 9000000000 --phone-mode digits10 \
  --probe-host https://freecom-app.mts.ru
```

## Примечания

- Авторизация идет по телефону и SMS-коду. Логина и пароля в приложении нет.
- Телефон отправляется как 10 цифр без `+7`.
- Возможна обязательность `X-Device-Token` (Firebase Installation ID). В демо можно указать токен через переменную окружения `VDOME_DEVICE_TOKEN`.
- Превью камеры получается через `watch_token` и `/api/v2/cameras/{camid}/preview/` с заголовком `Authorization: Acc <watch_token>`.
