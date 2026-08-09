# AnimeBox

Локальная аниме-библиотека для поиска, просмотра и поездок без интернета. AnimeBox запускается на вашем компьютере, сохраняет серии в обычные файлы и не требует аккаунта или облачного сервиса.

> **Статус:** ранний MVP. Сайты-источники меняются без предупреждения, поэтому отдельные провайдеры могут временно переставать работать.

## Что умеет

| Возможность | Статус |
|---|---|
| Поиск по нескольким источникам | ✅ |
| Карточка тайтла, серии и озвучки | ✅ |
| Онлайн-просмотр HLS через локальный proxy | ✅ |
| Загрузка серии или сезона | ✅ |
| Очередь, прогресс, отмена и повтор | ✅ |
| Локальная библиотека и офлайн-плеер | ✅ |
| Сохранение прогресса просмотра | ✅ |
| Оптимизация под Steam Deck | ✅ |
| Несколько сезонов и аудиодорожек в одном файле | В работе |

## Интерфейс

AnimeBox использует тёмный кинематографичный интерфейс с фиолетовым акцентом. После запуска откройте `http://127.0.0.1:8787`. На странице тайтла нажмите **Выбрать озвучку**, отметьте вариант для серии, затем запускайте просмотр или скачивание; глобальный список в настройках нужен только для автоматического выбора по умолчанию.

Кнопка **Выключить** в шапке корректно останавливает локальный сервер и освобождает порт `8787`. Простое закрытие вкладки браузера сервер не завершает: это защищает активные загрузки от случайного закрытия окна.

## Как устроен portable build

В архиве нет двух отдельных приложений. `AnimeBox.exe`/`AnimeBox` — один Python launcher с FastAPI backend и встроенными статическими файлами уже собранного React/TypeScript frontend. Node.js в архив не входит и на устройстве пользователя не запускается: браузер получает обычные HTML/CSS/JavaScript файлы от локального backend.

Каталог `.references/` содержит только локальные checkout исходных open-source проектов и не публикуется в Git. Скрипты установки и CI клонируют `anicli-api`, затем применяют отслеживаемый compatibility patch из `patches/`. Поэтому обязательные изменения больше не прячутся внутри полностью игнорируемого checkout.


## Portable Releases

Рекомендуемый способ для обычного пользователя — скачать готовый архив своей платформы из GitHub Releases. Python, Node.js, Git и системный ffmpeg не нужны: Python runtime, backend, собранный frontend, `anicli-api` и ffmpeg уже включены.

AnimeBox остаётся web-приложением: launcher поднимает приватный сервер на `http://127.0.0.1:8787` и открывает системный браузер. Отдельный desktop-интерфейс не устанавливается.

| Архив | Запуск |
|---|---|
| `AnimeBox-Windows-x64.zip` | распаковать и открыть `AnimeBox.exe` |
| `AnimeBox-Linux-x64.tar.gz` | Linux x86_64, включая Steam Deck/SteamOS; распаковать, выполнить `chmod +x AnimeBox && ./AnimeBox` |
| `AnimeBox-macOS-x64.zip` | Intel Mac; распаковать и открыть launcher |
| `AnimeBox-macOS-arm64.zip` | Apple Silicon; распаковать и открыть launcher |

Portable-папка уже содержит базовый `.env`, `data/`, `library/`, bundled ffmpeg и все runtime-зависимости. Интернет нужен только для поиска, получения новых потоков и загрузки. Уже скачанная библиотека, локальные постеры, MP4 и прогресс просмотра работают офлайн; внешние web-шрифты не используются.

При обновлении сохраните и перенесите в новую portable-папку:

- `.env` — настройки;
- `data/` — база, история и прогресс;
- `library/` — скачанные серии и постеры.

На неподписанном macOS build при первом запуске может потребоваться **Control-click → Open**. Portable archive нужно полностью распаковать перед запуском.

## Быстрый старт из исходников

Для запуска из исходников нужны Python 3.12+, Node.js 20+ с npm, Git и ffmpeg в `PATH`. Docker не требуется. Install-скрипт сам скачивает официальный `anicli-api` (MIT) в `.references/anicli-api`; остальные reference-проекты нужны только разработчикам.

### Windows 11

```powershell
git clone https://github.com/endercodezz/AnimeBox.git
cd AnimeBox
.\scripts\install.ps1
.\scripts\run.ps1
```

Можно запустить двойным кликом: сначала `scripts\install.cmd`, затем `scripts\run.cmd`. Диагностика: `scripts\check.cmd`.

При первом `install` или `run` автоматически создаётся базовый `.env` из `.env.example`. Существующий `.env` никогда не перезаписывается.

### macOS / Linux / Steam Deck

```bash
git clone https://github.com/endercodezz/AnimeBox.git
cd AnimeBox
chmod +x scripts/*.sh
./scripts/install.sh
./scripts/run.sh
```

### Режим разработки

```powershell
# Windows
.\scripts\run.ps1 -Dev
```

```bash
# macOS / Linux
./scripts/run.sh --dev
```

- Production UI + API: `http://127.0.0.1:8787`
- Vite UI в dev-режиме: `http://127.0.0.1:5173`
- OpenAPI: `http://127.0.0.1:8787/docs`

`run` собирает frontend, запускает API, ждёт успешный health-check и только затем открывает браузер. Используйте `--skip-build` / `-SkipBuild`, чтобы оставить существующую сборку, и `--no-browser` / `-NoBrowser`, чтобы не открывать браузер.

Проверить установку без запуска загрузки:

```powershell
.\scripts\check.ps1
```

```bash
./scripts/check.sh
```

## Настройка

При первом запуске `.env.example` копируется в `.env`. Основные параметры:

- `LIBRARY_PATH` — каталог загруженных серий;
- `DATABASE_URL` — SQLite URL;
- `HTTP_PROXY` — необязательный HTTP/SOCKS proxy для ограниченных источников;
- `PREFERRED_VOICEOVERS` — приоритет озвучек через запятую;
- `DEFAULT_QUALITY` — желаемое качество;
- `STEAM_DECK_CRF`, `STEAM_DECK_HEIGHT` — параметры перекодирования.

Большинство пользовательских параметров также доступны на странице **Настройки**.

## Где хранятся данные

```text
library/
└── Anime Name/
    ├── poster.jpg
    ├── metadata.json
    └── Season 1/
        ├── Episode 01.mp4
        └── Episode 02.mp4

data/
├── animebox.db
└── search_cache/
```

`library/`, база, cache и `.env` исключены из Git.

## Архитектура

```text
backend/
├── api/          # FastAPI endpoints
├── providers/    # adapters over anicli-api
├── downloader/   # durable SQLite queue and ffmpeg downloads
├── player/       # HLS/media reverse proxy
├── services/     # library, settings, ffmpeg helpers
├── database/     # async SQLAlchemy + SQLite
├── models/       # persistence models
└── schemas/      # Pydantic API contracts

frontend/src/
├── api/          # typed API client
├── components/   # shared UI
└── pages/        # search, library, anime, player, downloads, settings
```

Backend: Python, FastAPI, async SQLAlchemy, SQLite, Pydantic, httpx. Frontend: React, TypeScript, Tailwind CSS, Vite, hls.js.

## Проверки

```bash
# Backend
.venv/Scripts/python.exe -m pytest -q          # Windows
.venv/bin/python -m pytest -q                  # macOS/Linux

# Frontend
cd frontend
npm run lint
npm run build
```

Для runtime-проверки запустите AnimeBox, найдите тайтл, откройте серию, загрузите её и затем воспроизведите через раздел **Библиотека**.

## Решение проблем

### `venv not found`

Запустите `scripts/install.ps1` или `scripts/install.sh`. Если окружение перенесли между каталогами или компьютерами, удалите `.venv` и повторите установку.

### Поиск работает, но поток не открывается

- попробуйте другую озвучку или источник;
- проверьте доступность сайта в вашем регионе;
- задайте `HTTP_PROXY` в `.env` или интерфейсе;
- изучите сообщения backend в терминале.

### `Search cache expired`

Повторите поиск тайтла и откройте его из новых результатов. AnimeBox не хранит вечные ссылки на страницы источников.

### Загрузка требует ffmpeg

Установите ffmpeg и убедитесь, что команда `ffmpeg -version` работает в новом терминале. HLS/DASH и оптимизация Steam Deck без ffmpeg недоступны.

### Источник внезапно перестал работать

Провайдер мог изменить HTML/API либо быть недоступен у вашего интернет-провайдера. Если таймауты возникают только для одного домена, а остальные источники отвечают, portable build не сломан — это сетевой маршрут или блокировка конкретного источника. При необходимости задайте HTTP/SOCKS proxy в настройках. Не редактируйте `.references/anicli-api` вручную: пересоздайте checkout через скрипт установки, а compatibility-изменения храните в `patches/`.

## Правовые сведения

AnimeBox — локальный клиент и не размещает медиаконтент. Используйте приложение только для контента и источников, доступ к которым разрешён применимым законодательством и правилами сервиса. Пользователь отвечает за выбор источников и сохранение файлов.

## Credits

AnimeBox использует или изучает наработки:

- [anicli-api](https://github.com/vypivshiy/anicli-api) — извлечение каталога, серий, озвучек и потоков;
- [ani-cli-ru](https://github.com/vypivshiy/ani-cli-ru) — UX и reverse-proxy подход;
- [HakuNeko](https://github.com/manga-download/hakuneko) — архитектура коннекторов и загрузок;
- [Sonarr](https://github.com/Sonarr/Sonarr) — идеи устойчивой очереди, импорта и медиатеки.

Подробные лицензии и границы переиспользования: [THIRD_PARTY.md](THIRD_PARTY.md).
