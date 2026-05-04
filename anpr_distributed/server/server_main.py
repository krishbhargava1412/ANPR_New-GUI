"""ANPR Server — Uvicorn entry point."""
import uvicorn
from server.config import SERVER_HOST, SERVER_PORT

if __name__ == "__main__":
    uvicorn.run(
        "server.api.main:create_app",
        factory=True,
        host=SERVER_HOST,
        port=SERVER_PORT,
        reload=False,
        workers=2,       # 2 workers is fine for 4-5 concurrent users
        log_level="info",
    )
