# Vision — OCR + YOLOv8 License Plate Detection

A PyQt6-based desktop application for real-time license plate detection using YOLOv8 and OCR via Tesseract.

## Features

- **Camera Management** — Connect to multiple camera feeds, scan and add cameras to a grid
- **License Plate Detection** — YOLOv8-based detection with bounding box overlay
- **OCR** — Tesseract integration for extracting plate text
- **Live Log** — Real-time detection log with deduplication
- **Dark Theme** — Modern dark UI with yellow accents

## Tech Stack

- **PyQt6** — GUI framework
- **OpenCV** — Camera capture
- **ultralyticsplus** — YOLOv8 detection model (`keremberke/yolov8n-license-plate-detection`)
- **pytesseract** — OCR engine (requires Tesseract binary)

## Folder Structure

```
ocr_app/
├── main.py                 # Application entry point
├── requirements.txt        # Python dependencies
├── tesseract/
│   └── tesseract.exe      # Tesseract OCR binary
├── app/
│   ├── __init__.py
│   ├── ui/
│   │   ├── main_window.py  # Main window with sidebar navigation
│   │   ├── sidebar.py      # Navigation sidebar
│   │   └── styles.py       # Dark theme stylesheet
│   ├── camera/
│   │   ├── camera_page.py   # Camera management UI
│   │   ├── camera_worker.py # Background thread for camera capture
│   │   └── camera_tile.py   # Individual camera feed widget
│   ├── detection/
│   │   ├── detection_page.py  # Detection page with feed + log
│   │   └── plate_pipeline.py  # YOLOv8 + OCR processing thread
│   └── utils/
│       └── log_panel.py    # Detection log widget
```

## Requirements

- Python 3.9+
- Tesseract OCR binary bundled in `tesseract/` folder

Install dependencies:

```bash
pip install -r requirements.txt
```

## Usage

```bash
python main.py
```

## Navigation

| Page | Description |
|------|-------------|
| Dashboard | System overview, quick process, drop zone |
| Cameras | Add/remove camera feeds |
| Detection | Live YOLOv8 + OCR on selected camera |
| OCR | (Placeholder) |
| Pipeline | (Placeholder) |
| History | (Placeholder) |
| Settings | (Placeholder) |
| About | (Placeholder) |

## Configuration

- Detection confidence threshold: `0.4` (in `app/detection/plate_pipeline.py`)
- Model: `keremberke/yolov8n-license-plate-detection`
- OCR whitelist: Alphanumeric only
- Tesseract path: `tesseract/tesseract.exe` (relative to project root)
