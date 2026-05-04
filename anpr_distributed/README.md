# ANPR Distributed System — Jetson Edge + DRDO Server

## Architecture

```
┌─────────────────────┐         HTTP/REST          ┌──────────────────────────┐
│   JETSON EDGE NODE  │ ──────────────────────────▶ │    DRDO CENTRAL SERVER   │
│                     │                             │                          │
│  • 4× Camera RTSP   │  Detection JSON + Snapshots │  • FastAPI Backend       │
│  • YOLOv8 (TensorRT)│                             │  • PostgreSQL Database   │
│  • PaddleOCR        │  ◀──── Watchlist Sync ────── │  • JWT Authentication    │
│  • Store & Forward  │                             │  • Multi-user Dashboard  │
│  • Local Watchlist  │                             │  • RBAC (5 roles)        │
└─────────────────────┘                             └──────────────────────────┘
```

## Folder Structure

```
anpr_distributed/
├── edge/                    # Runs on Jetson
│   ├── config.py            # Edge configuration
│   ├── ingestion.py         # Camera RTSP capture (4 cameras)
│   ├── inference.py         # YOLOv8 + PaddleOCR inference
│   ├── plate_processing.py  # Plate text normalization, vote tracker
│   ├── store_forward.py     # Local buffer for network resilience
│   ├── watchlist_cache.py   # Local watchlist cache
│   ├── edge_main.py         # Main entry point for Jetson
│   └── requirements.txt     # Jetson-specific dependencies
│
├── server/                  # Runs on DRDO Server
│   ├── config.py            # Server configuration
│   ├── database/
│   │   ├── models.py        # SQLAlchemy models (PostgreSQL)
│   │   ├── session.py       # Async DB session factory
│   │   └── migrations.py    # Schema init + seed data
│   ├── auth/
│   │   ├── jwt_handler.py   # JWT token creation/validation
│   │   ├── password.py      # Argon2 password hashing
│   │   └── rbac.py          # Role-based access control
│   ├── api/
│   │   ├── main.py          # FastAPI app factory
│   │   ├── routes_auth.py   # Login/register endpoints
│   │   ├── routes_detections.py   # Detection history endpoints
│   │   ├── routes_cameras.py      # Camera management
│   │   ├── routes_watchlist.py    # Watchlist CRUD
│   │   ├── routes_users.py        # User management (admin)
│   │   ├── routes_dashboard.py    # Dashboard stats
│   │   └── routes_edge.py         # Edge node data ingestion
│   ├── server_main.py       # Uvicorn entry point
│   └── requirements.txt     # Server-specific dependencies
│
└── shared/                  # Shared code between edge & server
    ├── schemas.py           # Pydantic models for API payloads
    └── plate_utils.py       # Plate normalization (shared logic)
```

## Quick Start

### Server (DRDO Machine)
```bash
cd server
pip install -r requirements.txt
python server_main.py
```

### Edge (Jetson)
```bash
cd edge
pip install -r requirements.txt
python edge_main.py
```
