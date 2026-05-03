# Vision — OCR + YOLOv8 License Plate Detection

A PyQt6-based desktop application for real-time license plate detection using YOLOv8 and OCR via PaddleOCR.

## Features

- **Camera Management** — Connect to multiple camera feeds, scan and add cameras to a grid
- **License Plate Detection** — YOLOv8-based detection with bounding box overlay
- **OCR** — PaddleOCR integration for extracting plate text (via Awiros backend)
- **Live Log** — Real-time detection log with deduplication, watchlist matching, and alerts
- **User Interface** — Modern light UI with professional card-based components and multi-threaded video overlay
- **Role-Based Access Control** — Secure user authentication with SQLite database

## Tech Stack

- **PyQt6** — GUI framework
- **OpenCV** — Camera capture, proxy-resolution inference, image processing
- **ultralytics** — YOLOv8 detection model (`keremberke/yolov8n-license-plate-detection`)
- **PaddleOCR** — Deep learning framework for OCR
- **SQLAlchemy** — Database ORM for user management and watchlist system

## Folder Structure

```
ANPR_New-GUI/
├── main.py                 # Application entry point
├── requirements.txt        # Python dependencies
├── app/
│   ├── __init__.py
│   ├── camera/             # Camera management and background capture thread
│   ├── detection/          # YOLOv8 + PaddleOCR processing and overlay rendering
│   ├── services/           # Application state and runtime services
│   ├── storage/            # SQLite database, auth session, storage path config
│   ├── ui/                 # Main window, pages, login, dark/light theme styles
│   └── utils/              # Log panel and helper components
```

## Requirements

- Python 3.9+

### Setup Dependencies

1. **Install python packages**:
   ```bash
   pip install -r requirements.txt
   ```

   For an NVIDIA GPU setup, install the CUDA profile instead:
   ```bash
   pip install -r requirements-gpu.txt
   ```

2. **PaddleOCR Module**:
   The `ppocr` module is already vendored directly into the `app/detection` folder, making the repository completely self-contained. No external cloning is required.

## Usage

```bash
python main.py
```

## Navigation

| Page | Description |
|------|-------------|
| Dashboard | System overview, active alerts, quick metrics |
| Cameras | Add, edit or remove camera feeds |
| Live Feed | Multi-threaded live YOLOv8 + OCR inference on active cameras |
| Watchlist | Threat-level management mapped to SQLite database |
| History | Past detection logs and records |
| Settings | System configuration (confidence threshold, proxy-resolution, storage) |
| About | Information about the software |

## Configuration

- **Detection Confidence Threshold**: Configurable via the Settings UI (default typically `0.4`)
- **Proxy-Resolution Inference**: Downsamples frames for detection to improve FPS. Configurable in Settings.
- **Model used**: `keremberke/yolov8n-license-plate-detection`
- **OCR Engine**: Propelled by PaddlePaddle backend using Awiros configs.
