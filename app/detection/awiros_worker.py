from __future__ import annotations

import pickle
import struct
import sys

from app.detection.legacy_backend import AwirosAnprReader


def _read_exact(stream, size: int) -> bytes:
    chunks = bytearray()
    while len(chunks) < size:
        chunk = stream.read(size - len(chunks))
        if not chunk:
            raise EOFError
        chunks.extend(chunk)
    return bytes(chunks)


def _recv(stream):
    size = struct.unpack(">I", _read_exact(stream, 4))[0]
    return pickle.loads(_read_exact(stream, size))


def _send(stream, payload) -> None:
    data = pickle.dumps(payload, protocol=pickle.HIGHEST_PROTOCOL)
    stream.write(struct.pack(">I", len(data)))
    stream.write(data)
    stream.flush()


def main() -> int:
    reader = AwirosAnprReader()
    stdin = sys.stdin.buffer
    stdout = sys.stdout.buffer
    while True:
        try:
            payload = _recv(stdin)
        except EOFError:
            return 0
        if payload is None:
            return 0
        try:
            result = reader.readtext(payload)
            _send(stdout, {"result": result, "error": None})
        except Exception as exc:  # noqa: BLE001
            _send(stdout, {"result": None, "error": f"{type(exc).__name__}: {exc}"})


if __name__ == "__main__":
    raise SystemExit(main())
