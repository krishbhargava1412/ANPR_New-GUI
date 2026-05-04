# ANPR System: Jetson + DRDO Server Architecture Plan

Based on the requirements (Jetson edge inference, DRDO server for 4-5 concurrent users, 4 cameras), the current monolithic desktop architecture needs to be split into a **Distributed Edge-Cloud Architecture**.

Here is the detailed breakdown of changes needed and additional recommendations for production readiness.

---

## 1. Architectural Split: Edge vs. Server

The application must be physically and logically divided into two separate components:

### A. The Jetson Edge Node (Inference Hub)
The Jetson should be completely headless (no GUI) and dedicated purely to video processing and inference.
*   **Ingestion:** Connects to the 4 camera RTSP streams.
*   **Inference:** Runs the YOLOv8 and PaddleOCR models.
*   **Data Transmission:** Sends JSON payloads (metadata: plate text, confidence, bbox, timestamp) and cropped JPEGs to the DRDO server via a REST API or MQTT.
*   **NO UI:** The PyQt6 UI (`detection_page.py`, etc.) must **not** run on the Jetson. It wastes precious memory and CPU cycles.

### B. The DRDO Central Server (Backend & Database)
This server acts as the central brain and user portal.
*   **Database:** Migrate from SQLite to **PostgreSQL**. SQLite is not suitable for 4-5 concurrent users reading/writing simultaneously (it will lock and crash).
*   **Backend API:** Run a FastAPI application to receive detection data from the Jetson and serve data to the users.
*   **Web Frontend:** Serve a React/Next.js dashboard (as proposed in the re-architecture docs) so the 4-5 operators can access the system via their web browsers without installing any software.

---

## 2. Jetson-Specific Optimizations (Crucial for 4 Cameras)

Handling 4 cameras simultaneously on an ARM-based Jetson requires specific optimizations, otherwise, the system will lag and overheat.

1.  **TensorRT Conversion (Must Do):** You cannot run standard PyTorch `.pt` models efficiently on a Jetson. You must convert the YOLOv8 model to a TensorRT engine (`.engine` format). This will easily double or triple your FPS.
    *   *Action:* Run `yolo export model=yolov8n.pt format=engine workspace=4 half=True` on the Jetson.
2.  **Batching:** Configure your inference pipeline to batch frames from the 4 cameras (Batch Size = 4). Processing 4 frames simultaneously is much faster than processing them 1 by 1.
3.  **Hardware Decoding:** Ensure OpenCV or your RTSP ingestion script is using GStreamer with NVIDIA hardware decoding (`nvv4l2decoder`), not the CPU decoder.
4.  **Power Mode:** Ensure the Jetson is set to `MAXN` power mode (using `nvpmodel`) to unlock full GPU performance.

---

## 3. Handling Multi-User Access (4-5 People)

1.  **Role-Based Access Control (RBAC):** Since multiple logins are required, implement roles (e.g., `Admin`, `Operator`, `Viewer`). The FastAPI backend should issue JWT tokens upon login.
2.  **Concurrency Handling:** The DRDO server's API needs to be asynchronous (`async def`) so that if all 5 users click "Export History" or view the live feed simultaneously, the server does not freeze.

---

## 4. Additional Recommended Changes (The "More" You Should Do)

To make this a true defense-grade, production-ready system, you should implement the following:

### A. Store-and-Forward (Network Resilience)
*   **The Problem:** What happens if the network cable between the Jetson and the DRDO server is unplugged or the network drops? You lose plate detections.
*   **The Solution:** Implement a local SQLite database or Redis queue *on the Jetson itself*. When a plate is detected, save it locally first. Then, a background thread tries to push it to the DRDO server. If the server is unreachable, it keeps the data locally and bulk-syncs it once the connection is restored.

### B. Watchlist Caching at the Edge
*   If an alert vehicle passes, you don't want the Jetson to wait for a network response from the DRDO server to trigger an alarm.
*   **The Solution:** The Jetson should periodically download and cache the Watchlist locally. It checks plates against its local cache to trigger immediate edge-level alerts (e.g., sounding a siren or flashing a light connected to Jetson GPIO pins).

### C. Smart Video Streaming Strategy
*   **The Problem:** Sending 4 raw, high-resolution live video feeds from the Jetson to the DRDO server just so 4 users can watch them will destroy your network bandwidth.
*   **The Solution:**
    *   **Option 1:** The users' web browsers pull the RTSP stream *directly* from the IP cameras, bypassing the Jetson completely. The Jetson only sends the bounding box metadata, and the web browser draws the boxes over the video.
    *   **Option 2:** The Jetson drops the video quality to 480p and serves highly compressed MJPEG streams exclusively for viewing purposes.

### D. Thermal Throttling Management
*   Jetsons get very hot under 100% GPU load. If they overheat, they shut down.
*   **The Solution:** Write a small script that monitors Jetson `tegrastats` (temperature). If the temp exceeds 80°C, the system should automatically drop the camera frame rate from 15 FPS to 5 FPS to cool down, ensuring the system stays online.
