# TTS Service

Локальный сервис озвучки больших текстовых документов. Загружаешь PDF/DOCX/PPTX/TXT — получаешь MP3 с приятной русской озвучкой.

## Особенности

- Работает с длинными документами (10–100+ страниц)
- Русские голоса (Светлана, Дмитрий) через Microsoft Edge TTS
- Простой веб-интерфейс с drag & drop
- Прогресс-бар и асинхронная обработка
- Чанкинг по границам предложений (без обрывов слов)

## Установка

Требования: Python 3.10+, [ffmpeg](https://ffmpeg.org/download.html) в PATH.

```bash
pip install -r requirements.txt
```

## Запуск

```bash
python main.py
```

Открой http://localhost:8765 в браузере.

## API

- `POST /upload` — загрузить документ (multipart `file`, опционально `voice`). Возвращает `{job_id}`.
- `GET /status/{job_id}` — статус обработки и прогресс.
- `GET /download/{job_id}` — скачать готовый MP3.
- `GET /voices` — список доступных голосов.

## Структура

```
tts-service/
├── main.py              # FastAPI сервер
├── document_parser.py   # Извлечение текста (PDF/DOCX/PPTX/TXT)
├── tts_engine.py        # Edge TTS + чанкинг + ffmpeg
├── static/index.html    # Веб-интерфейс
├── uploads/             # Временные загрузки
├── outputs/             # Сгенерированные MP3
└── requirements.txt
```

## Поддерживаемые форматы

| Формат | Библиотека   |
|--------|--------------|
| PDF    | PyMuPDF      |
| DOCX   | python-docx  |
| PPTX   | python-pptx  |
| TXT    | (нативно)    |
