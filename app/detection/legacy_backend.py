from __future__ import annotations

import csv
import importlib.util
import logging
import os
import pickle
import re
import struct
import subprocess
import string
import atexit
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from threading import Lock
import sys

import cv2
import numpy as np

from app.storage import (
    get_snapshots_dir,
    get_logs_dir,
    get_watchlist_path,
    get_plate_log_path,
    get_awiros_anpr_dir,
    get_awiros_model_dir,
    get_awiros_dict_path,
    get_model_path,
    ensure_storage_dirs,
)


LOGGER = logging.getLogger("anpr_new_gui.detection")

APP_ROOT = Path(__file__).resolve().parents[2]
ASSETS_DIR = APP_ROOT / "assets"
PADDLEOCR_SOURCE_DIR = APP_ROOT.parent / "PaddleOCR"
OCR_DIR = get_awiros_anpr_dir()
OCR_MODEL_DIR = get_awiros_model_dir()
OCR_DICT_PATH = get_awiros_dict_path()
OCR_CONFIG_PATH = OCR_MODEL_DIR / "inference.yml"
OCR_WEIGHTS_PATH = OCR_MODEL_DIR / "model.safetensors"
LEGACY_LICENSE_PLATE_MODEL_PATH = get_model_path("LicensePlateDetector.pt")

PLATE_REGEX = r"^(?=.*[A-Z])(?=.*[0-9])[A-Z0-9]{6,10}$"
STRICT_PLATE_REGEX = r"^[A-Z]{2}[0-9]{2}[A-Z]{1,3}[0-9]{4}$"
OCR_MIN_SCORE = 0.35
LIVE_VOTE_MIN_HITS = 2
LIVE_VOTE_TTL = 30
DEFAULT_CONFIDENCE_THRESHOLD = 0.5

dict_char_to_int = {
    "O": "0",
    "I": "1",
    "J": "3",
    "A": "4",
    "G": "6",
    "S": "5",
}

dict_int_to_char = {
    "0": "O",
    "1": "I",
    "3": "J",
    "4": "A",
    "6": "G",
    "5": "S",
}

VALID_STATE_CODES = {
    "AN", "AP", "AR", "AS", "BH", "BR", "CG", "CH", "DD", "DL", "DN", "GA",
    "GJ", "HP", "HR", "JH", "JK", "KA", "KL", "LA", "LD", "MH", "ML", "MN",
    "MP", "MZ", "NL", "OD", "PB", "PY", "RJ", "SK", "TN", "TR", "TS", "UK",
    "UP", "WB",
}

_reader = None
_model = None
_reader_lock = Lock()
_model_lock = Lock()
_watchlist_cache: set[str] = set()
_watchlist_mtime: float = -1.0
_paddle_dll_handles: list[object] = []
_ocr_process = None


def ensure_runtime_dirs() -> None:
    ensure_storage_dirs()


def validate_detection_runtime() -> None:
    missing: list[str] = []
    for module_name, label in (
        ("cv2", "opencv-python"),
        ("torch", "torch"),
        ("ultralytics", "ultralytics"),
        ("yaml", "PyYAML"),
        ("paddle", "paddlepaddle"),
        ("safetensors", "safetensors"),
    ):
        if importlib.util.find_spec(module_name) is None:
            missing.append(label)

    if missing:
        raise RuntimeError(
            "Missing runtime dependencies: " + ", ".join(missing)
        )

    if not OCR_DICT_PATH.exists():
        raise FileNotFoundError(f"Awiros OCR dictionary not found: {OCR_DICT_PATH}")
    if not OCR_CONFIG_PATH.exists():
        raise FileNotFoundError(f"Awiros OCR config not found: {OCR_CONFIG_PATH}")
    if not OCR_WEIGHTS_PATH.exists():
        raise FileNotFoundError(
            f"Awiros OCR weights not found: {OCR_WEIGHTS_PATH}"
        )
    if not PADDLEOCR_SOURCE_DIR.exists():
        raise FileNotFoundError(
            "PaddleOCR source directory not found at "
            f"{PADDLEOCR_SOURCE_DIR}. Clone the official PaddleOCR repo there."
        )

    resolve_plate_model_path()


def resolve_plate_model_path() -> Path:
    from app.services.app_runtime import load_ui_settings

    settings = load_ui_settings()
    configured_name = str(settings.get("model_name", "LicensePlateDetector.pt")).strip()
    if configured_name:
        configured_path = get_model_path(configured_name)
        if configured_path.exists():
            return configured_path

    if LEGACY_LICENSE_PLATE_MODEL_PATH.exists():
        return LEGACY_LICENSE_PLATE_MODEL_PATH

    legacy_fallback = APP_ROOT / "assets" / "models" / "LicensePlateDetector.pt"
    if legacy_fallback.exists():
        return legacy_fallback

    raise FileNotFoundError(
        "Legacy plate model not found at "
        f"{LEGACY_LICENSE_PLATE_MODEL_PATH}"
    )


def _load_awiros_config() -> dict[str, object]:
    import yaml

    if not OCR_CONFIG_PATH.exists():
        return {}
    with OCR_CONFIG_PATH.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        return {}
    return data


def _preferred_ocr_device() -> str:
    try:
        return _preferred_torch_device()
    except Exception:
        return "cpu"


def _prepare_paddle_windows_runtime() -> None:
    if os.name != "nt":
        return

    nvidia_root = Path(sys_prefix_site_packages()) / "nvidia"
    if not nvidia_root.exists():
        return

    for subdir in nvidia_root.iterdir():
        if not subdir.is_dir():
            continue
        for folder_name in ("bin", "lib"):
            candidate = subdir / folder_name
            if not candidate.exists():
                continue
            try:
                handle = os.add_dll_directory(str(candidate))
                _paddle_dll_handles.append(handle)
            except (AttributeError, FileNotFoundError, OSError):
                pass
            current_path = os.environ.get("PATH", "")
            if str(candidate) not in current_path:
                os.environ["PATH"] = str(candidate) + os.pathsep + current_path


def sys_prefix_site_packages() -> str:
    import site

    candidates = []
    try:
        candidates.extend(site.getsitepackages())
    except Exception:
        pass
    user_site = getattr(site, "getusersitepackages", lambda: None)()
    if user_site:
        candidates.append(user_site)
    for candidate in candidates:
        if (
            candidate
            and "site-packages" in candidate.lower()
            and Path(candidate).exists()
        ):
            return candidate
    return str(
        Path(__file__).resolve().parents[2] / ".venv" / "Lib" / "site-packages"
    )


def _preferred_paddle_device() -> str:
    if os.name == "nt":
        try:
            from importlib import metadata

            metadata.version("paddlepaddle-gpu")
            return "gpu:0"
        except Exception:
            return "cpu"
    try:
        _prepare_paddle_windows_runtime()
        import paddle

        if paddle.is_compiled_with_cuda():
            return "gpu:0"
    except Exception:
        return "cpu"
    return "cpu"


def _get_paddle_device() -> str:
    try:
        return _preferred_paddle_device()
    except Exception:
        return "cpu"


class AwirosAnprReader:
    def __init__(self) -> None:
        self._config = _load_awiros_config()
        self._characters = self._load_characters()
        self._blank_idx = 0
        self._backend = self._build_backend()

    def _load_characters(self) -> list[str]:
        chars = [
            line.strip("\r\n")
            for line in OCR_DICT_PATH.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        if " " not in chars:
            chars.append(" ")
        return chars

    def _build_backend(self):
        _prepare_paddle_windows_runtime()
        import paddle
        import yaml
        from safetensors import safe_open

        import sys

        if str(PADDLEOCR_SOURCE_DIR) not in sys.path:
            sys.path.insert(0, str(PADDLEOCR_SOURCE_DIR))

        from ppocr.modeling.architectures import build_model

        rec_cfg = self._config.get("Rec", {})
        self._drop_score = float(rec_cfg.get("drop_score", OCR_MIN_SCORE))
        self._input_shape = tuple(
            int(part.strip())
            for part in str(rec_cfg.get("rec_image_shape", "3,48,320")).split(",")
        )
        self._device = _get_paddle_device()
        paddle.set_device(self._device)

        config_path = PADDLEOCR_SOURCE_DIR / "configs" / "rec" / "PP-OCRv5" / "PP-OCRv5_server_rec.yml"
        with config_path.open("r", encoding="utf-8") as handle:
            model_cfg = yaml.safe_load(handle)
        model_cfg["Architecture"]["Head"]["out_channels_list"] = {
            "CTCLabelDecode": len(self._characters) + 1,
            "NRTRLabelDecode": len(self._characters) + 4,
        }

        model = build_model(model_cfg["Architecture"])
        state_dict = {}
        with safe_open(str(OCR_WEIGHTS_PATH), framework="np") as handle:
            for key in handle.keys():
                state_dict[key] = paddle.to_tensor(handle.get_tensor(key))
        model.set_state_dict(state_dict)
        model.eval()
        return model

    def _prepare_image(self, image: np.ndarray) -> np.ndarray:
        if image is None or getattr(image, "size", 0) == 0:
            return np.zeros(self._input_shape, dtype=np.float32)

        if len(image.shape) == 2:
            image = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)

        img_c, img_h, img_w = self._input_shape
        resized = cv2.resize(image, (img_w, img_h), interpolation=cv2.INTER_LINEAR)
        normalized = resized.astype("float32").transpose((2, 0, 1)) / 255.0
        normalized -= 0.5
        normalized /= 0.5
        if normalized.shape[0] != img_c:
            normalized = normalized[:img_c]
        return normalized.astype(np.float32, copy=False)

    def _decode_ctc(self, probs: np.ndarray) -> tuple[str, float]:
        if probs.ndim != 2:
            return "", 0.0
        indices = probs.argmax(axis=1)
        scores = probs.max(axis=1)
        text_chars: list[str] = []
        text_scores: list[float] = []
        prev_idx = None
        for idx, score in zip(indices.tolist(), scores.tolist()):
            if idx == self._blank_idx or idx == prev_idx:
                prev_idx = idx
                continue
            char_idx = idx - 1
            if 0 <= char_idx < len(self._characters):
                text_chars.append(self._characters[char_idx])
                text_scores.append(float(score))
            prev_idx = idx
        if not text_chars:
            return "", 0.0
        return "".join(text_chars), float(sum(text_scores) / len(text_scores))

    def readtext(self, image) -> list[tuple[None, str, float]]:
        _prepare_paddle_windows_runtime()
        import paddle

        paddle.set_device(self._device)
        prepared = self._prepare_image(image)
        batch = paddle.to_tensor(np.expand_dims(prepared, axis=0))
        with paddle.no_grad():
            probs = self._backend(batch).numpy()[0]
        text, score = self._decode_ctc(probs)
        if text and score >= self._drop_score:
            return [(None, text, score)]
        return []


def create_awiros_reader():
    ensure_runtime_dirs()
    validate_detection_runtime()
    if os.name == "nt":
        return AwirosAnprProcessProxy()
    return AwirosAnprReader()


def get_reader():
    global _reader
    with _reader_lock:
        if _reader is None:
            _reader = create_awiros_reader()
        return _reader


def _allowlist_ultralytics_model_classes() -> None:
    import torch
    import ultralytics.nn.tasks as ultralytics_tasks

    add_safe_globals = getattr(torch.serialization, "add_safe_globals", None)
    if add_safe_globals is None:
        return
    allowed_names = [
        "BaseModel",
        "DetectionModel",
        "SegmentationModel",
        "ClassificationModel",
        "PoseModel",
        "OBBModel",
    ]
    allowed_objects = [
        getattr(ultralytics_tasks, name)
        for name in allowed_names
        if hasattr(ultralytics_tasks, name)
    ]
    add_safe_globals(allowed_objects)


def _preferred_torch_device() -> str:
    import torch

    if torch.cuda.is_available():
        return "cuda:0"
    mps = getattr(torch.backends, "mps", None)
    if mps is not None and torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def _get_safe_device() -> str:
    try:
        return _preferred_torch_device()
    except Exception:
        return "cpu"


def current_runtime_devices() -> dict[str, str]:
    return {
        "yolo": _get_safe_device(),
        "ocr": _get_paddle_device(),
    }


def _shutdown_ocr_process() -> None:
    global _ocr_process

    process = _ocr_process
    if process is not None and process.poll() is None:
        try:
            _ocr_send_message(process.stdin, None)
        except Exception:
            pass
        try:
            process.wait(timeout=2)
        except Exception:
            pass
    if process is not None and process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=2)
        except Exception:
            pass
    _ocr_process = None


def _ocr_send_message(stream, payload) -> None:
    data = pickle.dumps(payload, protocol=pickle.HIGHEST_PROTOCOL)
    stream.write(struct.pack(">I", len(data)))
    stream.write(data)
    stream.flush()


def _ocr_read_exact(stream, size: int) -> bytes:
    chunks = bytearray()
    while len(chunks) < size:
        chunk = stream.read(size - len(chunks))
        if not chunk:
            raise EOFError("OCR worker pipe closed")
        chunks.extend(chunk)
    return bytes(chunks)


def _ocr_receive_message(stream):
    size = struct.unpack(">I", _ocr_read_exact(stream, 4))[0]
    return pickle.loads(_ocr_read_exact(stream, size))


class AwirosAnprProcessProxy:
    def __init__(self) -> None:
        self._lock = Lock()
        self._ensure_process()

    def _ensure_process(self) -> None:
        global _ocr_process

        if _ocr_process is not None and _ocr_process.poll() is None:
            return

        _ocr_process = subprocess.Popen(
            [sys.executable, "-m", "app.detection.awiros_worker"],
            cwd=str(APP_ROOT),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            bufsize=0,
        )

    def readtext(self, image) -> list[tuple[None, str, float]]:
        self._ensure_process()
        with self._lock:
            if _ocr_process is None or _ocr_process.stdin is None or _ocr_process.stdout is None:
                raise RuntimeError("OCR worker failed to start")
            _ocr_send_message(_ocr_process.stdin, image)
            payload = _ocr_receive_message(_ocr_process.stdout)
            error = payload.get("error")
            if error:
                raise RuntimeError(error)
            return payload.get("result", [])


atexit.register(_shutdown_ocr_process)


def load_plate_model():
    from ultralytics import YOLO
    import torch

    _allowlist_ultralytics_model_classes()
    model_path = resolve_plate_model_path()
    original_torch_load = torch.load
    device = _get_safe_device()

    def trusted_torch_load(*args, **kwargs):
        kwargs.setdefault("weights_only", False)
        return original_torch_load(*args, **kwargs)

    torch.load = trusted_torch_load
    try:
        model = YOLO(str(model_path))
        try:
            model.to(device)
        except Exception:
            model.to("cpu")
        return model
    finally:
        torch.load = original_torch_load


def get_plate_model():
    global _model
    with _model_lock:
        if _model is None:
            _model = load_plate_model()
        return _model


def loaded_model_path() -> str:
    return str(resolve_plate_model_path())


def license_complies_format(text: str) -> bool:
    """Return True if *text* matches a valid plate format.

    Ten-character plates are validated against the Indian positional format
    (AA##AA####). Plates of 6–9 characters are accepted if they match the
    configurable PLATE_REGEX from settings.
    """
    if len(text) == 10:
        return (
            (text[0] in string.ascii_uppercase or text[0] in dict_int_to_char)
            and (text[1] in string.ascii_uppercase or text[1] in dict_int_to_char)
            and (text[2].isdigit() or text[2] in dict_char_to_int)
            and (text[3].isdigit() or text[3] in dict_char_to_int)
            and (text[4] in string.ascii_uppercase or text[4] in dict_int_to_char)
            and (text[5] in string.ascii_uppercase or text[5] in dict_int_to_char)
            and (text[6].isdigit() or text[6] in dict_char_to_int)
            and (text[7].isdigit() or text[7] in dict_char_to_int)
            and (text[8].isdigit() or text[8] in dict_char_to_int)
            and (text[9].isdigit() or text[9] in dict_char_to_int)
        )
    return bool(re.match(PLATE_REGEX, text))


def format_license(text: str) -> str:
    """Apply position-based OCR-correction for 10-char Indian plates.

    For plates shorter than 10 characters (allowed by PLATE_REGEX) the text is
    returned as-is because the positional correction map only applies to the
    Indian AA##AA#### format.
    """
    if len(text) != 10:
        return text
    license_plate_ = ""
    mapping = {
        0: dict_int_to_char,
        1: dict_int_to_char,
        4: dict_int_to_char,
        5: dict_int_to_char,
        2: dict_char_to_int,
        3: dict_char_to_int,
        6: dict_char_to_int,
        7: dict_char_to_int,
        8: dict_char_to_int,
        9: dict_char_to_int,
    }
    for index in range(10):
        license_plate_ += mapping[index].get(text[index], text[index])
    return license_plate_


def normalize_plate_text(text: str) -> str | None:
    text = text.upper().replace(" ", "")
    if not text:
        return None
    if len(text) == 10:
        if not license_complies_format(text):
            return None
        return format_license(text)
    if license_complies_format(text):
        return text
    return None


def preprocess_plate_crop(license_plate_crop):
    if license_plate_crop is None or getattr(license_plate_crop, "size", 0) == 0:
        return license_plate_crop
    image = license_plate_crop
    if len(image.shape) == 2:
        image = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
    height, width = image.shape[:2]
    if min(height, width) < 32:
        image = cv2.resize(image, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)
    return image


def read_license_plate(license_plate_crop):
    reader = get_reader()
    processed_crop = preprocess_plate_crop(license_plate_crop)
    detections = reader.readtext(processed_crop)
    best_text = None
    best_score = 0.0
    for _, text, score in detections:
        score = float(score or 0.0)
        if score < OCR_MIN_SCORE:
            continue
        normalized = normalize_plate_text(text)
        if normalized and score > best_score:
            best_text = normalized
            best_score = score
    if best_text is not None:
        return best_text, best_score
    return None, None


def detect_plates_in_frame(model, frame, confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD) -> list[dict[str, object]]:
    detections: list[dict[str, object]] = []
    try:
        predictions = model.predict(frame, conf=confidence_threshold, verbose=False)
        boxes = predictions[0].boxes
    except Exception as exc:  # noqa: BLE001
        LOGGER.warning("Model inference failed on frame: %s", exc)
        return detections
    for box in boxes:
        conf = float(box.conf[0])
        if conf < confidence_threshold:
            continue
        cls_id = int(box.cls[0])
        x1, y1, x2, y2 = map(int, box.xyxy[0])
        if x2 <= x1 or y2 <= y1:
            continue
        plate_crop = frame[y1:y2, x1:x2].copy()
        try:
            plate_text, ocr_score = read_license_plate(plate_crop)
        except Exception as exc:  # noqa: BLE001
            LOGGER.warning("OCR failed on crop [%d %d %d %d]: %s", x1, y1, x2, y2, exc)
            plate_text, ocr_score = None, None
        detections.append(
            {
                "bbox": (x1, y1, x2, y2),
                "confidence": conf,
                "class_id": cls_id,
                "label": getattr(model, "names", {}).get(cls_id, "plate"),
                "plate_text": plate_text,
                "ocr_score": ocr_score,
                "plate_crop": plate_crop,
            }
        )
    return detections


class PlateVoteTracker:
    def __init__(self, min_hits: int = LIVE_VOTE_MIN_HITS, ttl: int = LIVE_VOTE_TTL):
        self.min_hits = min_hits
        self.ttl = ttl
        self._tick = 0
        self._store: dict[tuple[str, int, int], dict[str, object]] = {}

    def _bucket_key(self, source: str, bbox: tuple[int, int, int, int]) -> tuple[str, int, int]:
        x1, y1, x2, y2 = bbox
        cx = (x1 + x2) // 2
        cy = (y1 + y2) // 2
        return (source, cx // 80, cy // 40)

    def register(self, source: str, bbox: tuple[int, int, int, int], plate_text: str, confidence: float = 0.0) -> str | None:
        normalized = normalize_plate_text(plate_text)
        if not normalized:
            return None
        self._tick += 1
        key = self._bucket_key(source, bbox)
        slot = self._store.setdefault(key, {"votes": defaultdict(int), "best_conf": {}, "last_seen": self._tick})
        slot["last_seen"] = self._tick
        slot["votes"][normalized] += 1
        slot["best_conf"][normalized] = max(float(confidence or 0.0), slot["best_conf"].get(normalized, 0.0))
        self.prune()
        best_text, best_hits = max(
            slot["votes"].items(),
            key=lambda item: (item[1], slot["best_conf"].get(item[0], 0.0), item[0]),
        )
        if best_hits >= self.min_hits:
            return best_text
        return None

    def prune(self):
        cutoff = self._tick - self.ttl
        stale_keys = [key for key, slot in self._store.items() if slot["last_seen"] < cutoff]
        for key in stale_keys:
            self._store.pop(key, None)


def safe_stem(value: str) -> str:
    stem = Path(value).stem if value else "output"
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", stem).strip("._")
    return cleaned or "output"


def next_snapshot_path(plate_number: str, source: str, timestamp: datetime | None = None) -> Path:
    ensure_runtime_dirs()
    stamp = (timestamp or datetime.now()).strftime("%Y%m%d_%H%M%S")
    return get_snapshots_dir() / f"{safe_stem(source)}_{safe_stem(plate_number)}_{stamp}.png"


def save_plate_snapshot(plate_region, snapshot_path: Path) -> Path | None:
    if plate_region is None or getattr(plate_region, "size", 0) == 0:
        return None
    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(snapshot_path), plate_region)
    return snapshot_path


def load_watchlist() -> set[str]:
    global _watchlist_cache, _watchlist_mtime
    ensure_runtime_dirs()
    watchlist_path = get_watchlist_path()
    try:
        current_mtime = watchlist_path.stat().st_mtime
    except OSError:
        return set()
    if current_mtime == _watchlist_mtime:
        return _watchlist_cache
    _watchlist_mtime = current_mtime
    _watchlist_cache = {
        line.strip().upper()
        for line in watchlist_path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    }
    return _watchlist_cache


def is_watchlist_hit(plate_number: str) -> bool:
    return plate_number.upper() in load_watchlist()


def append_plate_log(
    plate_number: str,
    *,
    timestamp: datetime | None = None,
    source: str,
    confidence: float | None = None,
    snapshot_path: Path | None = None,
    watchlist_hit: bool = False,
) -> None:
    ensure_runtime_dirs()
    now = (timestamp or datetime.now()).strftime("%Y-%m-%d %H:%M:%S")
    with open(get_plate_log_path(), mode="a", newline="", encoding="utf-8") as file:
        csv.writer(file).writerow(
            [
                now,
                plate_number,
                source,
                "" if confidence is None else f"{confidence:.4f}",
                str(snapshot_path or ""),
                "1" if watchlist_hit else "0",
            ]
        )
