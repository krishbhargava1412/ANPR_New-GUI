# ANPR System Re-Architecture — Production-Grade Design Document

> **Classification:** DRDO Internal — Engineering Review
> **Based on:** Full codebase audit of `ANPR_New-GUI` (May 2026)
> **Scope:** Complete system redesign from PyQt6 desktop → scalable web platform

---

## 1. Current Architecture Audit — Critical Findings

### What Exists Today

| Layer | Current Implementation | File(s) | Critical Issue |
|-------|----------------------|---------|----------------|
| **UI** | PyQt6 monolith (81KB `workspace_pages.py`) | `app/ui/*` | Desktop-bound, single user |
| **Camera** | `QThread`-based `CameraWorker` | `camera_worker.py` | One thread per camera, no backpressure |
| **Detection** | YOLOv8 via `ultralytics` | `legacy_backend.py` | Model loaded as global singleton with mutex |
| **OCR** | PaddleOCR via subprocess proxy | `awiros_worker.py` | Serialized pickle over stdin/stdout pipes |
| **Pipeline** | `PlatePipeline(QThread)` | `plate_pipeline.py` | Single pipeline thread for ALL cameras |
| **Storage** | SQLite via SQLAlchemy + CSV flat files | `database.py`, `app_runtime.py` | Dual-write (DB + CSV), no concurrency |
| **Auth** | PBKDF2 hashes in SQLite, in-memory session | `session.py` | No tokens, no expiry, single-process state |
| **Overlay** | `OverlayRenderer(QThread)` with queue | `overlay_renderer.py` | Coupled to Qt paint cycle |

### Architectural Coupling Map

```
MainWindow (PyQt6)
  ├── CameraWorker[N] ──(QThread signals)──→ DetectionPage
  │                                            ├── PlatePipeline (QThread)
  │                                            │    ├── get_plate_model() [global, mutex]
  │                                            │    ├── get_reader() [global, mutex]
  │                                            │    └── PlateVoteTracker [in-memory]
  │                                            ├── OverlayRenderer (QThread)
  │                                            └── LogPanel
  ├── SQLite DB (users, detections, watchlist, snapshots)
  └── CSV flat file (plate_log.csv) ← DUPLICATE of detection_history table
```

### Specific Bottlenecks Identified

1. **Single inference thread** — `PlatePipeline` is ONE `QThread`. Frame from camera 0 blocks camera 19.
2. **OCR subprocess serialization** — `AwirosAnprProcessProxy` uses pickle over pipes with a single `Lock()`. Every OCR call is serialized.
3. **Dual-write storage** — `append_plate_log()` writes CSV while `add_detection_history()` writes SQLite. No transaction guarantees between them.
4. **No frame dropping strategy** — `submit_frame()` copies every frame (`frame.copy()`), pipeline processes latest only. Wasted memory bandwidth.
5. **Vote tracker is in-memory** — `PlateVoteTracker._store` lost on restart. No persistence of confidence-building state.
6. **Global model singletons** — `_model` and `_reader` are module-level globals with `Lock()`. Cannot scale to multiple GPU workers.

---

## 2. Target Architecture

### High-Level System Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                        EDGE NODES (Optional)                        │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐                           │
│  │ Camera 1 │ │ Camera 2 │ │ Camera N │   RTSP/ONVIF              │
│  └────┬─────┘ └────┬─────┘ └────┬─────┘                           │
│       └─────────────┼───────────┘                                   │
│              ┌──────▼──────┐                                        │
│              │  Frame Grab  │  (edge pre-filter, optional)          │
│              │   Service    │                                        │
│              └──────┬──────┘                                        │
└─────────────────────┼───────────────────────────────────────────────┘
                      │ Frames (JPEG/raw) via Redis Streams
┌─────────────────────┼───────────────────────────────────────────────┐
│                 CENTRAL SERVER                                       │
│              ┌──────▼──────┐                                        │
│              │  Ingestion   │  asyncio + OpenCV                     │
│              │   Service    │  N cameras → M worker queues          │
│              └──────┬──────┘                                        │
│                     │ Frame queue (Redis Streams)                    │
│              ┌──────▼──────┐                                        │
│              │  Inference   │  YOLOv8 + PaddleOCR                   │
│              │   Workers    │  Multi-process, GPU-pinned             │
│              │  (1 per GPU) │                                        │
│              └──────┬──────┘                                        │
│                     │ Detection results                              │
│              ┌──────▼──────┐     ┌──────────────┐                   │
│              │  Backend     │────▶│  PostgreSQL   │                  │
│              │  API (Fast   │     │  + TimescaleDB│                  │
│              │   API)       │     └──────────────┘                   │
│              └──────┬──────┘                                        │
│                     │ REST + WebSocket                               │
│              ┌──────▼──────┐                                        │
│              │  Web Frontend│  React / Next.js                      │
│              │  Dashboard   │  Multi-user, RBAC                     │
│              └─────────────┘                                        │
└─────────────────────────────────────────────────────────────────────┘
```

### Design Principles

1. **Process isolation** — Inference workers are separate OS processes, not threads. GPU memory is not shared across the GIL.
2. **Queue-based decoupling** — Redis Streams between ingestion and inference. Enables backpressure, frame dropping, and horizontal scaling.
3. **Single source of truth** — PostgreSQL only. No CSV files. No dual-write.
4. **Stateless API** — FastAPI with JWT auth. Any instance can serve any request.
5. **Preserve ML stack** — YOLOv8 + PaddleOCR internals are untouched. Only the harness around them changes.

---

## 3. Component Design

### 3.1 Camera Ingestion Service

| Attribute | Detail |
|-----------|--------|
| **Responsibility** | Connect to RTSP/ONVIF/USB cameras, decode frames, push to queue |
| **Input** | Camera URLs/indices from DB config |
| **Output** | JPEG-encoded frames → Redis Stream per camera |
| **Tech** | Python `asyncio` + `opencv-python` + `redis-py` |
| **Concurrency** | One `asyncio.Task` per camera using `cv2.VideoCapture` in thread executor |

**Why asyncio, not threads:**
- Current `CameraWorker(QThread)` creates OS threads with Qt event loop overhead
- `asyncio` with `run_in_executor` for the blocking `cap.read()` call gives us cooperative scheduling for 100+ cameras on a single event loop
- Frame dropping is trivial: set `maxlen` on Redis Stream

**Key design decisions:**
```python
# Frame dropping via Redis Stream maxlen — keeps only latest N frames
await redis.xadd(f"frames:{camera_id}", {"jpeg": encoded}, maxlen=3)
```

- Frames are JPEG-encoded before queuing (10x smaller than raw BGR)
- Health monitoring: if a camera fails 10 reads, emit alert event, back off with exponential retry
- Camera config is read from PostgreSQL on startup and via pub/sub for live changes

### 3.2 Inference Engine (Workers)

| Attribute | Detail |
|-----------|--------|
| **Responsibility** | YOLOv8 detection + PaddleOCR recognition |
| **Input** | JPEG frames from Redis Stream |
| **Output** | Detection results → Redis Stream / direct DB write |
| **Tech** | Python multiprocessing workers, `ultralytics`, PaddlePaddle |
| **Concurrency** | 1 worker process per GPU (or per GPU fraction via MPS) |

**Why multiprocessing, not threading:**
- Python GIL prevents true parallel GPU kernel launches from threads
- Current system's `_model_lock` and `_reader_lock` serialize everything
- Separate processes get independent CUDA contexts
- Each worker loads its own model copy — memory cost ~400MB VRAM per YOLOv8s

**Pipeline within each worker:**
```
Read frame from Redis → JPEG decode → 
  YOLOv8 detect (640p proxy) → 
    For each plate bbox:
      Crop from original resolution →
      PaddleOCR recognize →
      normalize_plate_text() →
      Vote tracker check →
  Publish results
```

**Batching strategy:**
- Collect up to 4 frames (from different cameras) before running YOLOv8 inference
- YOLOv8's `model.predict()` already supports batch input
- Max wait: 50ms. If batch isn't full by then, run partial batch
- OCR runs per-crop (not batchable with current PaddleOCR architecture)

**Preserving existing logic:**
- `PlateVoteTracker` moves into the worker process, keyed by camera_id
- `normalize_plate_text()`, `license_complies_format()`, `format_license()` — reused verbatim
- `preprocess_plate_crop()` — reused verbatim
- Proxy resolution logic (downscale to 640p for detection, crop from original for OCR) — reused

### 3.3 Backend API Service

| Attribute | Detail |
|-----------|--------|
| **Responsibility** | REST API + WebSocket for real-time events |
| **Input** | HTTP requests from frontend, detection results from workers |
| **Output** | JSON responses, WebSocket events |
| **Tech** | FastAPI + Uvicorn + SQLAlchemy 2.0 async |

**API surface (key endpoints):**

```
Auth:
  POST /api/auth/login          → JWT token pair
  POST /api/auth/refresh        → refresh access token
  POST /api/auth/change-password

Cameras:
  GET    /api/cameras           → list configured cameras
  POST   /api/cameras           → add camera
  DELETE /api/cameras/{id}      → remove camera
  GET    /api/cameras/{id}/snapshot → latest frame JPEG

Detections:
  GET    /api/detections        → paginated, filtered
  GET    /api/detections/stats  → dashboard aggregations
  GET    /api/detections/export → CSV download
  WS     /api/ws/detections     → real-time detection stream

Watchlist:
  GET    /api/watchlist
  POST   /api/watchlist
  DELETE /api/watchlist/{plate}

Users (admin):
  GET    /api/users
  POST   /api/users
  PATCH  /api/users/{id}
  DELETE /api/users/{id}
```

**Auth redesign:**
- Current: `session.py` stores `_current_user` as module-level global — single process only
- New: JWT with `python-jose`, access token (15 min) + refresh token (7 days)
- Password hashing: upgrade from PBKDF2 to `argon2-cffi` (memory-hard, DoD recommended)
- RBAC middleware checking `role` claim in JWT against endpoint permissions

### 3.4 Web Frontend

| Attribute | Detail |
|-----------|--------|
| **Responsibility** | Multi-user dashboard, live feeds, alerts |
| **Tech** | React 18 + Vite, TanStack Query, Recharts, WebSocket |

**Why React, not Next.js:** This is an internal tool, not a public website. No SSR/SEO needed. Vite + React is simpler, faster to build, and has no server-side complexity.

**Key views (mapped from current PyQt pages):**

| Current PyQt Page | New Web View |
|-------------------|-------------|
| `DashboardPage` | `/dashboard` — stats cards, trend charts, recent detections |
| `DetectionPage` | `/live` — camera grid, live WebSocket detections, alert banner |
| `HistoryPage` | `/history` — searchable table with filters, export |
| `WatchlistPage` | `/watchlist` — CRUD table |
| `SettingsPage` | `/settings` — camera config, thresholds, user prefs |
| `UserManagementPage` | `/admin/users` — admin-only user CRUD |

**Live feed implementation:**
- Camera frames served as MJPEG stream from API (`/api/cameras/{id}/stream`)
- Detection overlays rendered client-side on HTML5 Canvas using WebSocket bbox data
- This eliminates the current `OverlayRenderer` thread and server-side OpenCV drawing

---

## 4. Data Flow

### Detection Flow (Hot Path)

```
Camera RTSP → [Ingestion] → Redis Stream "frames:{cam_id}"
                                    │
                              [Inference Worker]
                                    │
                              ┌─────▼─────┐
                              │ YOLOv8    │ (640p inference)
                              │ detect()  │
                              └─────┬─────┘
                                    │ bboxes
                              ┌─────▼─────┐
                              │ Crop from  │ (original resolution)
                              │ full frame │
                              └─────┬─────┘
                                    │ plate crops
                              ┌─────▼─────┐
                              │ PaddleOCR  │
                              │ readtext() │
                              └─────┬─────┘
                                    │ raw text
                              ┌─────▼─────┐
                              │ normalize  │ format_license()
                              │ + validate │ license_complies_format()
                              └─────┬─────┘
                                    │ clean plate text
                              ┌─────▼─────┐
                              │ VoteTracker│ (min 2 hits to confirm)
                              └─────┬─────┘
                                    │ confirmed plate
                              ┌─────▼─────┐
                              │ Watchlist  │ (PostgreSQL lookup, cached)
                              │ check      │
                              └─────┬─────┘
                                    │
                    ┌───────────────┼───────────────┐
                    ▼               ▼               ▼
              PostgreSQL      Redis Pub/Sub     Snapshot
              INSERT          → WebSocket       to disk
              detection       → all clients     (if enabled)
```

### Latency Budget (per frame, target <200ms)

| Stage | Budget | Notes |
|-------|--------|-------|
| Frame decode (JPEG) | 2ms | `cv2.imdecode` |
| YOLOv8 inference (640p, GPU) | 15-25ms | RTX 3060+ batch=1 |
| Crop extraction | <1ms | NumPy slice |
| PaddleOCR (per plate) | 30-50ms | Single crop, GPU |
| Post-processing + validation | <1ms | Regex + format |
| Vote tracker lookup | <1ms | In-memory dict |
| Watchlist check (cached) | <1ms | Redis/memory cache |
| DB write (async) | 5-10ms | Non-blocking, pooled |
| **Total (1 plate)** | **~60-90ms** | **Well within 200ms** |
| **Total (3 plates)** | **~120-170ms** | **OCR is per-crop** |

---

## 5. Concurrency Model

### Current vs Proposed

| Aspect | Current | Proposed |
|--------|---------|----------|
| Camera capture | `QThread` per camera | `asyncio.Task` + thread executor |
| Detection | Single `PlatePipeline(QThread)` | N worker processes (1/GPU) |
| OCR | Subprocess with pickle pipes | In-process within inference worker |
| Overlay rendering | `OverlayRenderer(QThread)` | Client-side Canvas (eliminated) |
| API serving | N/A (desktop app) | Uvicorn async workers |
| DB writes | Synchronous SQLAlchemy | Async SQLAlchemy 2.0 |

### Why This Split

**Ingestion = asyncio:**
Camera I/O is network-bound (RTSP) or device-bound (USB). `asyncio` with thread executor for the blocking `cap.read()` handles 100+ cameras on 2 threads. No GIL contention because there's no CPU work.

**Inference = multiprocessing:**
GPU inference is CPU+GPU bound. The GIL prevents parallel CUDA kernel launches from Python threads. Separate processes each get their own CUDA context. The current system's global `_model` with `Lock()` is the exact problem this solves.

**API = async (uvicorn):**
HTTP handling is I/O bound. FastAPI's async handlers serve 50+ concurrent users without thread pool exhaustion.

### Inter-Process Communication

```
Ingestion ──(Redis Streams)──→ Inference Workers
                                    │
                              (Redis Pub/Sub)
                                    │
                              ←── API Server ──→ Frontend (WebSocket)
                                    │
                              (SQLAlchemy async)
                                    │
                              PostgreSQL
```

**Why Redis Streams (not ZeroMQ, not RabbitMQ):**
- Already need Redis for caching (watchlist, session store)
- Streams have built-in consumer groups (multiple workers can share load)
- `MAXLEN` gives free frame dropping (backpressure)
- No additional infrastructure to manage
- Sub-millisecond latency for in-memory operations

