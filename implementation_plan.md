# ANPR Command Center — PyQt → Web (FastAPI + WebSocket + PostgreSQL)

Transform the monolithic PyQt6 desktop app into a distributed architecture with a Python backend (FastAPI + WebSocket), PostgreSQL as the **sole database and storage engine**, and a modern browser-based frontend.

## Architecture

```mermaid
graph TB
    subgraph "Browser Frontend"
        UI["SPA (HTML/CSS/JS)"]
        UI --> WS_C["WebSocket Client"]
        UI --> REST_C["REST API Client"]
    end
    
    subgraph "Python Backend (FastAPI)"
        SERVER["main_server.py"]
        SERVER --> REST["REST API Routes"]
        SERVER --> WS_S["WebSocket Manager"]
        
        REST --> AUTH["auth.py (JWT)"]
        REST --> API["API Route Modules"]
        
        WS_S --> CM["CameraManager"]
        CM --> CW["CameraWorker (threading)"]
        
        WS_S --> DM["DetectionManager"]
        DM --> PP["PlatePipeline (threading)"]
        PP --> LB["legacy_backend.py ✅ REUSED"]
        LB --> YOLO["YOLOv8 ✅"]
        LB --> OCR["PaddleOCR ✅"]
    end
    
    subgraph "PostgreSQL"
        PG_U["users"]
        PG_D["detection_log"]
        PG_W["watchlist"]
        PG_SN["snapshots (BYTEA)"]
        PG_SET["app_settings (JSONB)"]
        PG_CF["case_flags (JSONB)"]
    end
    
    REST --> PG_U & PG_D & PG_W & PG_SN & PG_SET & PG_CF
    WS_C <-->|"WebSocket"| WS_S
    REST_C <-->|"HTTP REST"| REST
```

---

## Key Design Decisions

> [!IMPORTANT]
> **PostgreSQL replaces ALL filesystem storage.** The current system uses 6 different file-based stores (CSV plate log, watchlist.txt, ui_settings.json, case_flags.json, snapshot PNGs on disk, SQLite DB). In the new architecture, **everything** lives in PostgreSQL — detection logs, settings, snapshots (as `BYTEA`), case flags (as `JSONB`). This eliminates filesystem dependencies, enables multi-server deployments, and makes backups trivial.

> [!IMPORTANT]
> **Zero detection logic rewrite.** All files under `app/detection/legacy_backend.py` (YOLO, OCR, plate formatting, vote tracker) are reused as-is. Only threading primitives change (`QThread` → `threading.Thread`).

> [!IMPORTANT]
> **WebSocket for real-time.** Camera frames are JPEG-encoded server-side and streamed as binary via WebSocket. Detection results, alerts, and telemetry flow as JSON.

> [!IMPORTANT]
> **JWT authentication.** Replaces in-memory session with stateless JWT tokens. Reuses `database.py` user/password verification.

---

## Storage Migration: Filesystem → PostgreSQL

This is the most impactful change. Here's every data source and where it moves:

| Current Store | Format | New Location | Strategy |
|---|---|---|---|
| `anpr.db` (SQLite) | SQLAlchemy tables | **PostgreSQL** `users`, `detection_history`, `snapshots`, `watchlist` | Change engine URL, add `psycopg2` driver |
| `detected_plates_log.csv` | CSV file | **PostgreSQL** `detection_log` table | **Eliminate CSV.** Rewrite `append_plate_log()` and `search_plate_log()` to use SQLAlchemy |
| `watchlist.txt` | Text file | **PostgreSQL** `watchlist` table | **Eliminate file.** Already has a DB table — consolidate `load_watchlist()` to use it exclusively |
| `ui_settings.json` | JSON file | **PostgreSQL** `app_settings` table (JSONB) | New table with `(key TEXT PK, value JSONB)` |
| `case_flags.json` | JSON file | **PostgreSQL** `case_flags` table | New table with `(plate TEXT PK, flagged BOOL, note TEXT, updated_at TIMESTAMP)` |
| `snapshots/*.png` | PNG files on disk | **PostgreSQL** `snapshots` table with `image_data BYTEA` | `save_plate_snapshot()` → encodes to PNG bytes → stores in DB |
| `storage_paths.json` | JSON config | **Environment variables** or `.env` file | Only `DATABASE_URL` and `MODELS_DIR` needed |

### New PostgreSQL Tables

```sql
-- Replaces detected_plates_log.csv (the CSV functions in app_runtime.py)
CREATE TABLE detection_log (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    plate_number VARCHAR(20) NOT NULL,
    source VARCHAR(100) NOT NULL,
    confidence FLOAT,
    watchlist_hit BOOLEAN DEFAULT FALSE,
    snapshot_id INTEGER REFERENCES snapshots(id),
    user_id INTEGER REFERENCES users(id)
);
CREATE INDEX idx_detection_log_plate ON detection_log(plate_number);
CREATE INDEX idx_detection_log_ts ON detection_log(timestamp);

-- Enhanced: image_data replaces filesystem snapshots
ALTER TABLE snapshots ADD COLUMN image_data BYTEA;
ALTER TABLE snapshots ADD COLUMN content_type VARCHAR(20) DEFAULT 'image/png';
-- Drop file_path after migration, or keep as optional fallback

-- Replaces ui_settings.json
CREATE TABLE app_settings (
    key VARCHAR(100) PRIMARY KEY,
    value JSONB NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Replaces case_flags.json
CREATE TABLE case_flags (
    plate_number VARCHAR(20) PRIMARY KEY,
    flagged BOOLEAN DEFAULT FALSE,
    note TEXT DEFAULT '',
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
```

### Files That Change Due to PostgreSQL

#### [MODIFY] [database.py](file:///d:/DRDO/ANPR_New-GUI/app/storage/database.py)
- Engine: `sqlite:///` → `postgresql://` via `DATABASE_URL` env var
- Add `DetectionLog` model (replaces CSV)
- Add `AppSettings` model (replaces JSON file)
- Add `CaseFlag` model (replaces JSON file)
- Add `image_data: LargeBinary` to `Snapshot` model
- Add new CRUD functions: `add_detection_log()`, `search_detection_log()`, `get_settings()`, `set_settings()`, `get_case_flags()`, `set_case_flag()`
- Add `get_snapshot_image()` → returns bytes from DB

#### [MODIFY] [storage/__init__.py](file:///d:/DRDO/ANPR_New-GUI/app/storage/__init__.py)
- **Massively simplified.** Remove all filesystem path functions (`get_plate_log_path`, `get_watchlist_path`, `get_ui_settings_path`, `get_snapshots_dir`, etc.)
- Keep only: `get_awiros_anpr_dir()`, `get_awiros_model_dir()`, `get_awiros_dict_path()`, `get_model_path()` (these reference bundled model files that must stay on disk)
- `init_storage()` → just calls `database.init_db()`
- Remove `platformdirs` dependency, `migrate_from_legacy()`, `save_storage_paths()`
- New: `get_database_url()` reads from env var or `.env` file

#### [MODIFY] [app_runtime.py](file:///d:/DRDO/ANPR_New-GUI/app/services/app_runtime.py)
This file has the **most changes** because it currently wraps all CSV/JSON file operations:

| Function | Current | New |
|---|---|---|
| `load_ui_settings()` | Reads `ui_settings.json` | Calls `database.get_settings()` |
| `save_ui_settings()` | Writes `ui_settings.json` | Calls `database.set_settings()` |
| `search_plate_log()` | Parses CSV file | Calls `database.search_detection_log()` |
| `recent_detections()` | Reads CSV tail | SQL `ORDER BY timestamp DESC LIMIT n` |
| `grouped_plate_history()` | Groups CSV rows in Python | SQL `GROUP BY plate_number` + Python post-processing |
| `dashboard_stats()` | Scans CSV + counts files | SQL aggregations |
| `trend_snapshot()` | Scans CSV with time windows | SQL `WHERE timestamp BETWEEN` |
| `clear_plate_log()` | Deletes CSV file | SQL `DELETE FROM detection_log` |
| `delete_history_entries()` | Rewrites CSV | SQL `DELETE FROM detection_log WHERE id IN (...)` |
| `load_case_flags()` | Reads `case_flags.json` | Calls `database.get_case_flags()` |
| `save_case_flag()` | Writes `case_flags.json` | Calls `database.set_case_flag()` |
| `watchlist_entries()` | Reads `watchlist.txt` | Calls `database.get_watchlist()` |
| `save_watchlist_entries()` | Writes `watchlist.txt` | Calls `database.add_watchlist_plate()` in loop |
| `clear_outputs()` | Deletes PNG files | SQL `DELETE FROM snapshots` |
| `delete_snapshot_file()` | `os.unlink()` | SQL `DELETE FROM snapshots WHERE id=` |

#### [MODIFY] [legacy_backend.py](file:///d:/DRDO/ANPR_New-GUI/app/detection/legacy_backend.py)
- `append_plate_log()` (line 776-798): Rewrite from CSV append → `database.add_detection_log()`
- `save_plate_snapshot()` (line 740-745): Rewrite from `cv2.imwrite()` → `cv2.imencode()` + `database.add_snapshot_blob()`
- `load_watchlist()` / `is_watchlist_hit()`: Already delegates to DB — just remove the CSV fallback path
- Remove imports: `csv`, `get_plate_log_path`, `get_snapshots_dir`

---

## Open Questions

> [!WARNING]
> **1. PostgreSQL hosting**: Will you run PostgreSQL locally (`localhost:5432`), in Docker, or use a managed service? This affects the connection string and setup instructions.
>
> **Recommendation**: Docker Compose with a `postgres:16` service for easy dev setup.

> [!WARNING]
> **2. Snapshot storage size**: Storing snapshots as `BYTEA` is simple but can bloat the DB. A single 640×480 PNG is ~100-300KB. At 1000 detections/day that's ~150MB/day. Options:
> - (A) `BYTEA` in PostgreSQL (simple, recommended for now)
> - (B) PostgreSQL Large Objects
> - (C) S3-compatible object storage with DB references
>
> **Recommendation**: Start with BYTEA. Migrate to S3 later if needed.

> [!WARNING]
> **3. Frame streaming resolution**: Should WebSocket video preview stream at 640p (saves bandwidth) or full resolution?

> [!WARNING]
> **4. Legacy PyQt code**: Delete or keep for reference?

---

## Proposed Folder Structure

```
d:\DRDO\ANPR_New-GUI\
├── assets/                          # ✅ UNCHANGED (models, awiros_anpr)
├── app/
│   ├── __init__.py                  # ✅ UNCHANGED
│   ├── camera/
│   │   ├── camera_worker.py         # 🔄 QThread → threading.Thread
│   │   ├── camera_manager.py        # 🆕 Orchestrates camera workers
│   │   ├── camera_page.py           # ❌ UNUSED (PyQt)
│   │   └── camera_tile.py           # ❌ UNUSED (PyQt)
│   ├── detection/
│   │   ├── legacy_backend.py        # 🔄 CSV/filesystem → database calls
│   │   ├── plate_pipeline.py        # 🔄 QThread → threading.Thread
│   │   ├── detection_manager.py     # 🆕 Orchestrates pipelines + WebSocket
│   │   ├── overlay_renderer.py      # 🔄 QThread → threading, QImage → cv2
│   │   ├── awiros_worker.py         # ✅ UNCHANGED
│   │   └── ppocr/                   # ✅ UNCHANGED
│   ├── services/
│   │   ├── __init__.py              # ✅ UNCHANGED
│   │   └── app_runtime.py           # 🔄 CSV/JSON → database queries
│   ├── storage/
│   │   ├── __init__.py              # 🔄 SIMPLIFIED (remove filesystem paths)
│   │   ├── database.py              # 🔄 SQLite→PostgreSQL, new models, new CRUD
│   │   └── session.py               # ✅ UNCHANGED
│   ├── utils/
│   │   └── log_panel.py             # ❌ UNUSED (PyQt)
│   ├── ui/                          # ❌ ENTIRE FOLDER UNUSED (PyQt)
│   │
│   ├── server/                      # 🆕 FastAPI Backend
│   │   ├── __init__.py
│   │   ├── main_server.py           # FastAPI app, lifespan, static mount
│   │   ├── auth.py                  # JWT login, middleware
│   │   ├── websocket_manager.py     # Connection manager, broadcast
│   │   ├── api/                     # REST routes
│   │   │   ├── __init__.py
│   │   │   ├── dashboard.py         # GET /api/dashboard/stats
│   │   │   ├── history.py           # GET/DELETE /api/history
│   │   │   ├── watchlist.py         # GET/POST/DELETE /api/watchlist
│   │   │   ├── settings.py          # GET/PUT /api/settings
│   │   │   ├── cameras.py           # Scan/start/stop cameras
│   │   │   ├── detection.py         # Start/stop/pause pipelines
│   │   │   ├── users.py             # Admin CRUD
│   │   │   ├── about.py             # System info
│   │   │   └── snapshots.py         # GET /api/snapshots/{id} (serves from DB)
│   │   └── ws/
│   │       └── feed_handler.py      # /ws/feed endpoint
│   │
│   └── web/                         # 🆕 Frontend SPA
│       ├── index.html
│       ├── css/styles.css
│       └── js/
│           ├── app.js               # Boot, router, auth check
│           ├── api.js               # fetch() with JWT
│           ├── ws.js                # WebSocket client
│           ├── auth.js              # Login modal, token storage
│           ├── router.js            # Hash-based SPA router
│           ├── components/          # sidebar, stat_card, alert_banner,
│           │                        # data_table, feed_canvas
│           └── pages/               # dashboard, detection, history,
│                                    # watchlist, settings, about, users
│
├── main.py                          # ❌ UNUSED (old PyQt entry)
├── run_server.py                    # 🆕 New entry point
├── .env                             # 🆕 DATABASE_URL, JWT_SECRET, etc.
├── docker-compose.yml               # 🆕 PostgreSQL service
├── requirements.txt                 # 🔄 MODIFIED
└── requirements-gpu.txt             # 🔄 MODIFIED
```

---

## Proposed Changes (grouped by component)

### Storage Layer (PostgreSQL Migration)

#### [MODIFY] [database.py](file:///d:/DRDO/ANPR_New-GUI/app/storage/database.py)
- Engine: read `DATABASE_URL` from env, default `postgresql://anpr:anpr@localhost:5432/anpr`
- New model `DetectionLog` — replaces CSV plate log
- New model `AppSettings` — replaces `ui_settings.json` (key/JSONB)
- New model `CaseFlag` — replaces `case_flags.json`
- Enhanced `Snapshot` — add `image_data: LargeBinary`, `content_type: String`
- New CRUD: `add_detection_log()`, `search_detection_log()`, `get_settings()`, `set_settings()`, `get_case_flags()`, `set_case_flag()`, `get_snapshot_image()`

#### [MODIFY] [storage/__init__.py](file:///d:/DRDO/ANPR_New-GUI/app/storage/__init__.py)
- Remove: `platformdirs`, all `get_*_path()` filesystem functions, `migrate_from_legacy()`, `save_storage_paths()`
- Keep: `get_awiros_anpr_dir()`, `get_awiros_model_dir()`, `get_awiros_dict_path()`, `get_model_path()` (model files stay on disk)
- New: `get_database_url()` from env

#### [MODIFY] [app_runtime.py](file:///d:/DRDO/ANPR_New-GUI/app/services/app_runtime.py)
- Rewrite all CSV-parsing functions (`search_plate_log`, `recent_detections`, `grouped_plate_history`, `dashboard_stats`, `trend_snapshot`, `clear_plate_log`, `delete_history_entries`) to use `database.search_detection_log()` and SQL aggregations
- Rewrite settings functions to use `database.get_settings()` / `database.set_settings()`
- Rewrite case flags to use `database.get_case_flags()` / `database.set_case_flag()`
- Rewrite `clear_outputs()` and `delete_snapshot_file()` to use SQL deletes
- Remove: all CSV/JSON file I/O, `get_plate_log_runtime_path()`, `get_case_flags_path()`, `get_settings_path()`

#### [MODIFY] [legacy_backend.py](file:///d:/DRDO/ANPR_New-GUI/app/detection/legacy_backend.py)
- `append_plate_log()`: CSV write → `database.add_detection_log()`
- `save_plate_snapshot()`: `cv2.imwrite()` → `cv2.imencode('.png')` + `database.add_snapshot_blob()`
- `load_watchlist()` / `is_watchlist_hit()`: remove file fallback, use DB exclusively
- Remove: `csv` import, `get_plate_log_path`, `get_snapshots_dir` imports

---

### Backend Server

#### [NEW] [run_server.py](file:///d:/DRDO/ANPR_New-GUI/run_server.py)
Entry point: loads `.env`, inits DB, launches uvicorn.

#### [NEW] [.env](file:///d:/DRDO/ANPR_New-GUI/.env)
```
DATABASE_URL=postgresql://anpr:anpr@localhost:5432/anpr
JWT_SECRET=<random-secret>
MODELS_DIR=./assets/models
```

#### [NEW] [docker-compose.yml](file:///d:/DRDO/ANPR_New-GUI/docker-compose.yml)
```yaml
services:
  postgres:
    image: postgres:16
    environment:
      POSTGRES_USER: anpr
      POSTGRES_PASSWORD: anpr
      POSTGRES_DB: anpr
    ports: ["5432:5432"]
    volumes: [pgdata:/var/lib/postgresql/data]
volumes:
  pgdata:
```

#### [NEW] [main_server.py](file:///d:/DRDO/ANPR_New-GUI/app/server/main_server.py)
FastAPI app: mounts static, includes API routers, registers `/ws/feed`, lifespan init.

#### [NEW] [auth.py](file:///d:/DRDO/ANPR_New-GUI/app/server/auth.py)
JWT auth: `POST /api/auth/login` → validates via `database.verify_user()` → returns JWT.

#### [NEW] [websocket_manager.py](file:///d:/DRDO/ANPR_New-GUI/app/server/websocket_manager.py)
Connection registry, camera subscriptions, frame/detection/alert broadcast.

#### [NEW] API route modules (9 files under `app/server/api/`)
dashboard, history, watchlist, settings, cameras, detection, users, about, snapshots — each calling existing `app_runtime` / `database` functions.

#### [NEW] [ws/feed_handler.py](file:///d:/DRDO/ANPR_New-GUI/app/server/ws/feed_handler.py)
WebSocket endpoint for frame streaming and real-time events.

---

### Threading Layer

#### [MODIFY] [camera_worker.py](file:///d:/DRDO/ANPR_New-GUI/app/camera/camera_worker.py)
`QThread` → `threading.Thread`, `pyqtSignal` → callbacks, `QMutex` → `threading.Lock`. Core OpenCV logic unchanged.

#### [NEW] [camera_manager.py](file:///d:/DRDO/ANPR_New-GUI/app/camera/camera_manager.py)
Manages all camera workers, routes frames to DetectionManager + WebSocket.

#### [MODIFY] [plate_pipeline.py](file:///d:/DRDO/ANPR_New-GUI/app/detection/plate_pipeline.py)
Same QThread → threading migration. Detection logic unchanged.

#### [NEW] [detection_manager.py](file:///d:/DRDO/ANPR_New-GUI/app/detection/detection_manager.py)
Orchestrates pipelines, calls `append_plate_log()` + `save_plate_snapshot()`, pushes to WebSocket.

#### [MODIFY] [overlay_renderer.py](file:///d:/DRDO/ANPR_New-GUI/app/detection/overlay_renderer.py)
`QThread` → `threading.Thread`, `QImage` → cv2 JPEG bytes.

---

### Frontend

#### [NEW] SPA shell + design system
- `index.html` — sidebar layout, content area, login modal
- `css/styles.css` — dark theme, glassmorphism, animations, responsive breakpoints

#### [NEW] JavaScript modules
- `app.js`, `api.js`, `ws.js`, `auth.js`, `router.js`
- Components: `sidebar`, `stat_card`, `alert_banner`, `data_table`, `feed_canvas`
- Pages: `dashboard`, `detection`, `history`, `watchlist`, `settings`, `about`, `users`

---

### WebSocket Protocol

```
Binary:  [4B camera_id] + [JPEG bytes]              → video frames

JSON:    { type: "detection", camera_id, plate, confidence, bbox, watchlist_hit, ... }
         { type: "alert", plate, camera_id, source, timestamp }
         { type: "telemetry", camera_id, fps, latency_ms, box_count }
         { type: "status", camera_id, message }
```

---

### Dependency Changes

#### [MODIFY] [requirements.txt](file:///d:/DRDO/ANPR_New-GUI/requirements.txt)
```diff
-PyQt6>=6.6.0
-platformdirs>=4.0.0
 opencv-python>=4.8.0
 numpy>=1.24.0
 Pillow>=10.0.0
+
+# ── Web Server ────────────────────────────────────────────
+fastapi>=0.115.0
+uvicorn[standard]>=0.30.0
+python-jose[cryptography]>=3.3.0
+python-multipart>=0.0.9
+python-dotenv>=1.0.0
+
+# ── PostgreSQL ────────────────────────────────────────────
+psycopg2-binary>=2.9.0
```

---

## Implementation Phases

| Phase | Scope | Key Deliverables |
|---|---|---|
| **1. PostgreSQL + Storage** | Database migration | New models, CRUD functions, rewrite `app_runtime.py` + `legacy_backend.py` I/O, `docker-compose.yml` |
| **2. Backend Server** | FastAPI core | `main_server.py`, JWT auth, all 9 API route modules, snapshot serving |
| **3. Threading** | Camera/detection | `camera_worker` + `plate_pipeline` → threading, `CameraManager`, `DetectionManager` |
| **4. WebSocket** | Real-time layer | `websocket_manager`, `feed_handler`, frame broadcast, detection push |
| **5. Frontend** | Browser SPA | `index.html`, CSS design system, all JS modules and pages |
| **6. Polish** | Integration | End-to-end testing, responsive design, `requirements.txt` update |

---

## Verification Plan

### Automated Tests
- `docker compose up -d` → PostgreSQL starts on 5432
- `python run_server.py` → server starts on 8000
- `curl POST /api/auth/login` → returns JWT
- `curl GET /api/dashboard/stats` → returns JSON from PostgreSQL
- `curl GET /api/snapshots/{id}` → returns PNG from database BYTEA
- WebSocket at `ws://localhost:8000/ws/feed` → receives frames

### Manual Verification
- Login flow in browser
- Live camera feed on canvas
- Detection results appear in real-time
- Watchlist alerts trigger
- History search with PostgreSQL-backed queries
- Snapshot images load from database
- Settings persist across server restarts
