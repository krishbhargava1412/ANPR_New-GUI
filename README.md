# Vision - OCR + YOLOv8 License Plate Detection

ANPR Command Center runs directly on the host machine. Docker is only kept as an optional PostgreSQL service.

## Features

- **Camera Management** - Connect to multiple camera feeds, scan and add cameras to a grid
- **License Plate Detection** - YOLOv8-based detection with bounding box overlay
- **OCR** - PaddleOCR integration for extracting plate text via the bundled Awiros pipeline
- **Live Log** - Real-time detection log with deduplication, watchlist matching, and alerts
- **User Interface** - Browser-based SPA with real-time canvas feed, detection controls, and live share sessions
- **Role-Based Access Control** - Secure user authentication with PostgreSQL-backed storage

## Tech Stack

- **FastAPI** - Local backend API and websocket server
- **Vanilla JS SPA** - Browser frontend served by FastAPI
- **OpenCV** - Camera capture, proxy-resolution inference, image processing
- **ultralytics** - YOLOv8 detection model (`keremberke/yolov8n-license-plate-detection`)
- **PaddleOCR** - OCR framework
- **SQLAlchemy** - Database ORM
- **PostgreSQL** - Persistent application storage

## Folder Structure

```text
ANPR_New-GUI/
|-- run_server.py
|-- run.bat
|-- requirements.txt
|-- requirements-gpu.txt
|-- docker-compose.yml
`-- app/
    |-- detection/
    |-- server/
    |-- services/
    |-- storage/
    `-- web/
```

## Requirements

- Python 3.9+
- PostgreSQL on `localhost:5432`

## Setup

1. Install Python packages:
   ```bash
   pip install -r requirements.txt
   ```

   For NVIDIA GPU systems:
   ```bash
   pip install -r requirements-gpu.txt
   ```

2. Start PostgreSQL.

   If you want Docker only for the database:
   ```bash
   docker compose up -d postgres
   ```

3. Review `.env`.

   The repo now targets a host-local database connection:
   ```env
   DATABASE_URL=postgresql://anpr:anpr@localhost:5432/anpr
   ```

4. Start the backend:
   ```bash
   python run_server.py
   ```

   On Windows you can also use:
   ```bash
   run.bat
   ```

## Notes

- The app itself is no longer containerized.
- `docker-compose.yml` exists only to provide PostgreSQL storage.
- The bundled `ppocr` module in `app/detection` keeps the OCR pipeline self-contained.
