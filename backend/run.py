"""
VYUHA Backend — Entry Point
Run with:  python run.py
"""
import sys
from pathlib import Path

import uvicorn

# Ensure backend root is on the Python path
sys.path.insert(0, str(Path(__file__).parent))

from app.config import settings  # noqa: E402

if __name__ == "__main__":
    print("=" * 55)
    print("  VYUHA — व्यूह  Traffic Event-Response System")
    print("=" * 55)
    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
        log_level="info",
    )
