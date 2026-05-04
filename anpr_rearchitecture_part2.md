# ANPR System Re-Architecture — Part 2

> Continuation: Database Design, Inference Pipeline, Deployment, Hardware, Trade-offs

---

## 6. Database Design

### Why PostgreSQL (not MySQL, not MongoDB)

| Requirement | PostgreSQL | SQLite (current) | MongoDB |
|-------------|-----------|-------------------|---------|
| Concurrent writers | ✅ MVCC, 1000s | ❌ Single writer | ✅ |
| Time-series queries | ✅ TimescaleDB ext | ❌ | ❌ |
| ACID transactions | ✅ | ✅ (limited) | ⚠️ |
| Full-text search | ✅ `tsvector` | ❌ | ✅ |
| JSON columns | ✅ `jsonb` | ❌ | ✅ |
| Async driver | ✅ `asyncpg` | ❌ | ✅ |
| Defense/govt adoption | ✅ Widely certified | ❌ | ⚠️ |

**TimescaleDB extension** is added specifically for `detections` — it's a hypertable that auto-partitions by time. This makes "detections in the last 5 minutes" queries (currently `trend_snapshot()` scanning entire CSV) nearly instant.

### Schema

```sql
-- ━━━ Users ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CREATE TABLE users (
    id            SERIAL PRIMARY KEY,
    username      VARCHAR(50) UNIQUE NOT NULL,
    full_name     VARCHAR(100) NOT NULL DEFAULT '',
    password_hash VARCHAR(256) NOT NULL,  -- argon2id hash (includes salt)
    role          VARCHAR(20) NOT NULL DEFAULT 'operator'
                  CHECK (role IN ('admin','manager','operator','gate_keeper','viewer')),
    created_by    INTEGER REFERENCES users(id),
    is_active     BOOLEAN NOT NULL DEFAULT true,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_login    TIMESTAMPTZ,
    
    -- Migration note: maps directly from current User model
    -- Removed: separate 'salt' column (argon2id embeds salt in hash)
);

-- ━━━ Cameras ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
-- NEW: cameras are first-class entities, not JSON strings in settings
CREATE TABLE cameras (
    id            SERIAL PRIMARY KEY,
    name          VARCHAR(100) NOT NULL,
    source_url    VARCHAR(500) NOT NULL,  -- RTSP URL, device index, or file path
    source_type   VARCHAR(20) NOT NULL DEFAULT 'rtsp'
                  CHECK (source_type IN ('rtsp','onvif','usb','file')),
    location      VARCHAR(200),           -- physical location description
    is_active     BOOLEAN NOT NULL DEFAULT true,
    config        JSONB NOT NULL DEFAULT '{}',  -- fps, resolution, roi, etc.
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    added_by      INTEGER REFERENCES users(id),
    
    -- Migration note: replaces camera_indices + ip_camera_urls from ui_settings.json
);

-- ━━━ Detections (TimescaleDB hypertable) ━━━━━
CREATE TABLE detections (
    id            BIGSERIAL,
    camera_id     INTEGER NOT NULL REFERENCES cameras(id),
    plate_number  VARCHAR(20) NOT NULL,
    confidence    REAL,
    ocr_score     REAL,
    bbox          INTEGER[4],             -- [x1, y1, x2, y2]
    snapshot_path VARCHAR(500),
    watchlist_hit BOOLEAN NOT NULL DEFAULT false,
    metadata      JSONB DEFAULT '{}',     -- vote count, processing time, etc.
    detected_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
    PRIMARY KEY (id, detected_at)
    -- Migration note: replaces BOTH detection_history table AND plate_log.csv
);

-- Convert to TimescaleDB hypertable (auto-partitions by week)
SELECT create_hypertable('detections', 'detected_at', chunk_time_interval => INTERVAL '7 days');

-- Indexes for common query patterns
CREATE INDEX idx_detections_plate ON detections (plate_number, detected_at DESC);
CREATE INDEX idx_detections_camera ON detections (camera_id, detected_at DESC);
CREATE INDEX idx_detections_watchlist ON detections (detected_at DESC) WHERE watchlist_hit = true;

-- ━━━ Watchlist ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CREATE TABLE watchlist (
    id            SERIAL PRIMARY KEY,
    plate_number  VARCHAR(20) UNIQUE NOT NULL,
    threat_level  VARCHAR(20) NOT NULL DEFAULT 'medium'
                  CHECK (threat_level IN ('low','medium','high','critical')),
    added_by      INTEGER NOT NULL REFERENCES users(id),
    notes         TEXT,
    added_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at    TIMESTAMPTZ,            -- NEW: optional auto-expiry
    
    -- Migration note: maps from current Watchlist model + watchlist.txt file
);

-- ━━━ Audit Logs ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
-- NEW: replaces anpr_app.log file with structured audit trail
CREATE TABLE audit_logs (
    id            BIGSERIAL PRIMARY KEY,
    user_id       INTEGER REFERENCES users(id),
    action        VARCHAR(50) NOT NULL,   -- 'login','watchlist_add','export', etc.
    target_type   VARCHAR(50),            -- 'user','camera','detection','watchlist'
    target_id     VARCHAR(100),
    details       JSONB DEFAULT '{}',
    ip_address    INET,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ━━━ Case Flags ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
-- Replaces case_flags.json file
CREATE TABLE case_flags (
    id            SERIAL PRIMARY KEY,
    plate_number  VARCHAR(20) UNIQUE NOT NULL,
    flagged       BOOLEAN NOT NULL DEFAULT true,
    note          TEXT DEFAULT '',
    flagged_by    INTEGER REFERENCES users(id),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

### Migration Path from Current System

| Current Source | Target Table | Strategy |
|----------------|-------------|----------|
| `users` (SQLite) | `users` (PG) | Direct row copy, rehash passwords with argon2 |
| `detection_history` (SQLite) | `detections` | Map `user_id` → `camera_id`, copy |
| `detected_plates_log.csv` | `detections` | Parse CSV, deduplicate against SQLite rows |
| `watchlist.txt` + `watchlist` (SQLite) | `watchlist` | Merge unique plates |
| `ui_settings.json` camera fields | `cameras` | Parse `camera_indices` + `ip_camera_urls` |
| `case_flags.json` | `case_flags` | Direct JSON parse + insert |

---

## 7. Inference + OCR Pipeline

### Frame Handling Strategy

```
┌─────────────────────────────────────────────────┐
│              Inference Worker Process             │
│                                                   │
│  ┌─────────┐    ┌──────────┐    ┌────────────┐  │
│  │ Redis    │───▶│ Batch    │───▶│ YOLOv8     │  │
│  │ Consumer │    │ Collector│    │ predict()  │  │
│  │ Group    │    │ (max=4,  │    │ batch mode │  │
│  │          │    │ wait=50ms│    │ 640p       │  │
│  └─────────┘    └──────────┘    └─────┬──────┘  │
│                                       │          │
│                                  ┌────▼─────┐   │
│                                  │ Per-bbox  │   │
│                                  │ OCR loop  │   │
│                                  └────┬─────┘   │
│                                       │          │
│                    ┌─────────────┬─────┴────┐    │
│                    ▼             ▼          ▼    │
│              Vote Tracker   Watchlist   Snapshot  │
│              (in-memory)    (cached)    (async)   │
│                    │             │                │
│                    └──────┬──────┘                │
│                           ▼                       │
│                    Results → Redis Pub/Sub         │
│                           → PostgreSQL (async)     │
└─────────────────────────────────────────────────┘
```

### Batching Logic

```python
async def batch_collector(redis_consumer, max_batch=4, max_wait_ms=50):
    """Collect frames into batches for efficient GPU utilization."""
    batch = []
    deadline = time.monotonic() + max_wait_ms / 1000
    
    while len(batch) < max_batch:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        msg = await redis_consumer.read(timeout_ms=int(remaining * 1000))
        if msg:
            batch.append(msg)
    
    return batch  # May be 1-4 frames
```

**Why batch=4, wait=50ms:**
- YOLOv8 batch=4 on RTX 3060 takes ~30ms vs ~25ms for batch=1. Nearly free parallelism.
- 50ms wait adds at most 50ms to latency (worst case: 1 slow camera). Still within 200ms budget.
- At 20 cameras × 6 FPS effective rate = 120 frames/sec. Batch of 4 fills in ~33ms on average.

### GPU Utilization Strategy

| Scenario | GPUs | Workers | Cameras Supported |
|----------|------|---------|-------------------|
| Pilot | 1× RTX 3060 | 1 worker | 10-15 cameras |
| Production | 1× RTX 4090 | 1 worker | 25-40 cameras |
| High-scale | 2× A100 | 2 workers | 80-100 cameras |

**Frame skip integration:**
- Current system uses `frame_skip=5` (process every 5th frame)
- In new system: ingestion service publishes at effective FPS (e.g., 6 FPS from 30 FPS source)
- Worker never waits — always processes whatever is in the queue
- Redis Stream `MAXLEN=3` ensures worker always gets recent frame, never stale

### OCR Pipeline Optimization

**Preprocessing (preserved from current `preprocess_plate_crop`):**
```python
def preprocess_plate_crop(crop):
    if crop.shape[0] < 32 or crop.shape[1] < 32:
        crop = cv2.resize(crop, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)
    # Grayscale conversion removed — PaddleOCR handles internally
    return crop
```

**Post-processing chain (preserved + enhanced):**
```
Raw OCR text
  → uppercase + strip spaces
  → PLATE_REGEX check: ^(?=.*[A-Z])(?=.*[0-9])[A-Z0-9]{6,10}$
  → If 10 chars: positional format check (AA##AA####)
  → If 10 chars: OCR correction mapping (O→0, I→1, etc.)
  → State code validation (VALID_STATE_CODES set)
  → Vote tracker: require 2+ consistent reads to confirm
  → Output: confirmed plate text or None
```

**False positive mitigation (improvements over current):**
1. **Confidence gating:** Current `OCR_MIN_SCORE = 0.35` is too low. Raise to `0.45` for production.
2. **State code validation:** Current code has `VALID_STATE_CODES` set but doesn't enforce it in the hot path. Add as mandatory first-2-char check for Indian plates.
3. **Temporal deduplication:** Don't log the same plate from the same camera within 30 seconds (current system lacks this — `PlateVoteTracker` only gates on confirmation, not re-logging).

---

## 8. Deployment Strategy

### Tier 1: Single-Node (Pilot / PoC)

```
┌─────────────────────────────────────────┐
│           Single Server                  │
│                                          │
│  ┌──────────┐  ┌──────────┐             │
│  │ Ingestion│  │ Inference│  1 GPU      │
│  │ (async)  │  │ (process)│             │
│  └────┬─────┘  └────┬─────┘             │
│       │              │                   │
│  ┌────▼──────────────▼────┐             │
│  │       Redis             │             │
│  └────────────┬───────────┘             │
│               │                          │
│  ┌────────────▼───────────┐             │
│  │    FastAPI + Uvicorn    │             │
│  └────────────┬───────────┘             │
│               │                          │
│  ┌────────────▼───────────┐             │
│  │     PostgreSQL          │             │
│  └────────────────────────┘             │
│                                          │
│  ┌────────────────────────┐             │
│  │  Nginx (reverse proxy) │             │
│  │  + static frontend     │             │
│  └────────────────────────┘             │
└──────────────────────────────────────────┘
```

**All services on one machine.** Managed with `systemd` units or a single `docker-compose.yml`. This is sufficient for 10-20 cameras.

### Tier 2: Distributed (Production)

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│  Edge Node 1 │     │  Edge Node 2 │     │  Edge Node N │
│  (camera LAN)│     │  (camera LAN)│     │  (camera LAN)│
│  Ingestion   │     │  Ingestion   │     │  Ingestion   │
└──────┬───────┘     └──────┬───────┘     └──────┬───────┘
       │                    │                    │
       └────────────┬───────┴────────────────────┘
                    │ WAN / VPN
       ┌────────────▼───────────────────────────┐
       │         Central Server                  │
       │  ┌──────────┐  ┌──────────┐            │
       │  │ Inference │  │ Inference│  2+ GPUs   │
       │  │ Worker 1  │  │ Worker 2 │            │
       │  └─────┬─────┘  └─────┬────┘            │
       │        └───────┬───────┘                 │
       │         Redis  │  PostgreSQL             │
       │         FastAPI│  Nginx                  │
       └────────────────┴─────────────────────────┘
```

**Edge nodes** are lightweight (Raspberry Pi 5 or Jetson Nano level). They only run the ingestion service — decode RTSP, encode to JPEG, push to Redis over VPN. No GPU needed at edge.

### Tier 3: Defense-Grade (High Availability)

- PostgreSQL: primary + streaming replica with automatic failover (Patroni)
- Redis: Sentinel for HA
- API: 2+ Uvicorn instances behind Nginx load balancer
- Inference: dedicated GPU servers, health-checked
- All traffic encrypted (mTLS between services)
- Air-gapped deployment option (no internet dependency)
- All containers signed and scanned

### Docker Compose (Tier 1 Reference)

```yaml
services:
  redis:
    image: redis:7-alpine
    ports: ["6379:6379"]
    volumes: ["redis_data:/data"]

  postgres:
    image: timescale/timescaledb:latest-pg16
    environment:
      POSTGRES_DB: anpr
      POSTGRES_USER: anpr
      POSTGRES_PASSWORD_FILE: /run/secrets/db_password
    volumes: ["pg_data:/var/lib/postgresql/data"]
    ports: ["5432:5432"]

  ingestion:
    build: ./services/ingestion
    depends_on: [redis, postgres]
    environment:
      REDIS_URL: redis://redis:6379
      DATABASE_URL: postgresql+asyncpg://anpr@postgres/anpr
    restart: unless-stopped

  inference:
    build: ./services/inference
    depends_on: [redis, postgres]
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]
    environment:
      REDIS_URL: redis://redis:6379
      DATABASE_URL: postgresql+asyncpg://anpr@postgres/anpr
    restart: unless-stopped

  api:
    build: ./services/api
    depends_on: [redis, postgres]
    ports: ["8000:8000"]
    environment:
      REDIS_URL: redis://redis:6379
      DATABASE_URL: postgresql+asyncpg://anpr@postgres/anpr
      JWT_SECRET_FILE: /run/secrets/jwt_secret

  frontend:
    build: ./frontend
    ports: ["3000:80"]
    depends_on: [api]
```

---

## 9. Hardware Recommendations

### Minimum (Pilot — 10 cameras)

| Component | Specification | Est. Cost |
|-----------|--------------|-----------|
| CPU | Intel i7-12700 / AMD Ryzen 7 5800X | ₹25,000 |
| RAM | 32 GB DDR4 | ₹8,000 |
| GPU | NVIDIA RTX 3060 12GB | ₹25,000 |
| Storage | 1TB NVMe SSD | ₹7,000 |
| Network | 1 Gbps NIC | included |
| **Total** | | **~₹65,000** |

### Recommended (Production — 20-40 cameras)

| Component | Specification | Est. Cost |
|-----------|--------------|-----------|
| CPU | Intel Xeon W-2445 / AMD EPYC 7313 | ₹80,000 |
| RAM | 64 GB DDR5 ECC | ₹30,000 |
| GPU | NVIDIA RTX 4090 24GB | ₹1,60,000 |
| Storage | 2TB NVMe + 8TB HDD (snapshots) | ₹25,000 |
| Network | 10 Gbps NIC | ₹5,000 |
| UPS | 2KVA online | ₹25,000 |
| **Total** | | **~₹3,25,000** |

### High-Scale (Defense-Grade — 100+ cameras)

| Component | Specification | Est. Cost |
|-----------|--------------|-----------|
| CPU | 2× Intel Xeon Gold 6430 | ₹4,00,000 |
| RAM | 256 GB DDR5 ECC | ₹1,20,000 |
| GPU | 2× NVIDIA A100 80GB or L40S | ₹12,00,000 |
| Storage | RAID-10 NVMe array + NAS | ₹3,00,000 |
| Network | 25 Gbps + dedicated switch | ₹50,000 |
| HA | Redundant PSU, IPMI, hot-swap | included |
| Edge nodes | 5× Jetson Orin Nano (₹40K each) | ₹2,00,000 |
| **Total** | | **~₹23,00,000** |

---

## 10. Bottlenecks and Trade-offs

### Known Bottlenecks

| Bottleneck | Impact | Mitigation |
|-----------|--------|-----------|
| **PaddleOCR latency** | 30-50ms per crop, sequential per-plate | Cannot batch (architecture limitation). Mitigate by running OCR only on high-confidence detections (conf > 0.6) |
| **Redis memory** | Frames in Redis consume RAM | `MAXLEN=3` per stream. At 100 cameras × 3 frames × 50KB JPEG = 15MB. Negligible. |
| **PostgreSQL write throughput** | High detection rate → many INSERTs | Batch inserts every 500ms. TimescaleDB handles 100K inserts/sec easily. |
| **Network bandwidth (edge → central)** | 100 cameras × 6 FPS × 50KB = 30 MB/s | Acceptable on 1 Gbps. Compress to WebP for edge deployments. |
| **Model cold start** | YOLOv8 + PaddleOCR load takes 10-15s | One-time on worker start. Workers are long-lived processes. |

### Critical Trade-offs

| Decision | Trade-off | Justification |
|----------|----------|---------------|
| **PostgreSQL over MongoDB** | Less flexible schema, more setup | ACID guarantees matter for audit trails. TimescaleDB gives us time-series performance without a separate DB. Defense engineers expect relational. |
| **Redis Streams over Kafka** | Less durable, no replay | We don't need replay. Frames are ephemeral. Redis is already in-stack. Kafka adds operational complexity for zero benefit here. |
| **Multiprocessing over Kubernetes** | Manual scaling, no auto-healing | K8s is overkill for 1-3 GPU servers. `systemd` + health checks + alerting is sufficient. Revisit if scaling beyond 5 servers. |
| **React over PyQt web wrapper** | Full rewrite of UI | PyQt6 cannot be "web-ified." The 81KB `workspace_pages.py` is not portable. Clean break is faster than wrapping. |
| **JWT over session cookies** | Token management complexity | Stateless auth scales to multiple API instances. Session affinity with cookies breaks load balancing. |
| **Frame skip at ingestion, not inference** | Wastes camera bandwidth | Camera always streams at native FPS. We drop at ingestion, not after decode. Saves GPU cycles but not network. Acceptable trade-off — camera LANs are dedicated. |

### What NOT to Do

1. **Don't use gRPC for internal communication.** Redis pub/sub + HTTP is simpler and sufficient. gRPC adds protobuf compilation and debugging complexity for no latency gain on a single server.
2. **Don't implement ONNX conversion.** The current PyTorch + PaddlePaddle stack works. ONNX adds a conversion step and loses some operator support. Not worth it unless deploying to TensorRT on Jetson.
3. **Don't build a custom streaming server.** Use Nginx RTMP module or simple MJPEG endpoint for live camera views. Building a custom WebRTC server is months of work.
4. **Don't attempt real-time video recording in the inference pipeline.** Recording is a separate concern. Use `ffmpeg` to record RTSP streams directly to disk, independent of detection.

---

## 11. Implementation Roadmap

### Phase 1 — Foundation (4-6 weeks)
- [ ] Set up PostgreSQL + TimescaleDB with schema
- [ ] Migrate existing SQLite data
- [ ] Build FastAPI backend with auth (JWT + argon2)
- [ ] Port `legacy_backend.py` inference logic to standalone worker
- [ ] Basic React frontend (login, dashboard, history)

### Phase 2 — Core Pipeline (4-6 weeks)
- [ ] Redis Streams integration (ingestion → inference)
- [ ] Multi-process inference workers with batching
- [ ] WebSocket real-time detection feed
- [ ] Live camera MJPEG streaming endpoint
- [ ] Client-side detection overlay rendering

### Phase 3 — Production Hardening (3-4 weeks)
- [ ] Docker containerization + compose
- [ ] Health checks and auto-restart
- [ ] Audit logging
- [ ] Data retention policies (auto-delete old detections)
- [ ] Load testing (20 cameras, 50 concurrent users)
- [ ] Security audit (input validation, rate limiting, CORS)

### Phase 4 — Scale (optional, 2-4 weeks)
- [ ] Edge node ingestion service
- [ ] Multi-GPU worker scaling
- [ ] PostgreSQL replication
- [ ] Monitoring stack (Prometheus + Grafana)

---

> **Document ends.** This design is intended to be reviewed by defense engineers and should be treated as a living architecture document. All technology choices are justified against specific current-system bottlenecks identified through codebase analysis.
