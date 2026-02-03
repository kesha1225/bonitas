# Vdome API demo

Python-обертка и демо-веб-приложение для использования функций домофона и камер Vdome через API. Веб-демо — одна страница `/stream` с просмотром камеры и кнопкой открытия двери по 4-значному коду. Поток идет через RTSP → HLS при наличии `ffmpeg`, иначе показывается превью.

## Быстрый старт

Установка:

```bash
python -m pip install -e .
```

Подготовьте переменные окружения:

```bash
export VDOME_ACCESS_TOKEN="..."
export VDOME_REFRESH_TOKEN="..."      # опционально, для авто-рефреша
export VDOME_DEVICE_TOKEN="..."       # опционально

export VDOME_STREAM_USER="stream"
export VDOME_STREAM_PASSWORD="strong-pass"

export VDOME_STREAM_CAMERA_ID="123"   # опционально, если камер несколько
# или VDOME_STREAM_CAMERA_NAME="Entrance"

export VDOME_OPEN_CODE="1234"         # обязательный 4-значный код
export VDOME_INTERCOM_ID="456"        # опционально, если автосвязка не сработала
export VDOME_INTERCOM_LOCK="1"        # опционально, номер замка
```

Запуск демо:

```bash
uvicorn demo_app:app --reload
```

Откройте `http://127.0.0.1:8000/stream` и введите Basic Auth логин/пароль.
Для реального доступа используйте HTTPS (например, через reverse proxy).

## Использование библиотеки

```python
from vdome_api import VdomeClient

client = VdomeClient()
client.auth_init("9040580807")
# введите SMS код

tokens = client.auth_login("9040580807", "1234")

cameras = client.get_cameras(tokens.access_token)
print(cameras)
```

## Тестирование API через CLI

```bash
python tools/vdome_api_test.py init --phone +79040580807 --phone-mode digits10
python tools/vdome_api_test.py login --phone +79040580807 --code 1234 --phone-mode digits10
python tools/vdome_api_test.py cameras --access-token <token>
```

Для первичной диагностики хоста/пути:

```bash
python tools/vdome_api_test.py probe-init --phone +79040580807 --phone-mode digits10
```

Можно добавить дополнительные хосты:

```bash
python tools/vdome_api_test.py probe-init --phone +79040580807 --phone-mode digits10 \
  --probe-host https://freecom-app.mts.ru
```

## Примечания

- Авторизация идет по телефону и SMS-коду. Логина и пароля в приложении нет.
- Телефон отправляется как 10 цифр без `+7`.
- Возможна обязательность `X-Device-Token` (Firebase Installation ID). В демо можно указать токен через переменную окружения `VDOME_DEVICE_TOKEN`.
- Превью камеры получается через `watch_token` и `/api/v2/cameras/{camid}/preview/` с заголовком `Authorization: Acc <watch_token>`.
