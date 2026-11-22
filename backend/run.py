import os
import sys
import uvicorn

if __name__ == "__main__":
    raw_port = os.getenv("PORT", "").strip()

    # Also handle if --port was passed in sys.argv
    for i, arg in enumerate(sys.argv):
        if arg in ("--port", "-p") and i + 1 < len(sys.argv):
            raw_port = sys.argv[i + 1].strip()

    if not raw_port or raw_port.startswith("$") or not raw_port.isdigit():
        port = 8000
    else:
        try:
            port = int(raw_port)
        except (ValueError, TypeError):
            port = 8000

    print(f"Starting DukaanAI Backend on 0.0.0.0:{port}...", flush=True)
    uvicorn.run("app.main:app", host="0.0.0.0", port=port, log_level="info")
