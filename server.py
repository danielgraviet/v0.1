"""
Alpha SRE — dashboard server.

Serves the web frontend and exposes stub API endpoints that will
be wired to AlphaRuntime in later phases.
"""

import uvicorn
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

app = FastAPI(title="Alpha SRE", version="0.1.0", docs_url=None, redoc_url=None)

app.mount("/static", StaticFiles(directory="frontend/static"), name="static")


@app.get("/")
async def dashboard() -> FileResponse:
    return FileResponse("frontend/index.html")


# ---------------------------------------------------------------------------
# Stub API endpoints — will wire to AlphaRuntime in Phase 3+
# ---------------------------------------------------------------------------


@app.post("/api/analyze")
async def analyze(body: dict) -> dict:
    """Accept a raw IncidentInput payload and run the full pipeline."""
    return {
        "status": "not_implemented",
        "message": "Signal extraction not yet wired up. Coming in Phase 3.",
    }


@app.get("/api/health")
async def health() -> dict:
    return {"status": "ok", "version": "0.1.0"}


if __name__ == "__main__":
    uvicorn.run("server:app", host="127.0.0.1", port=8000, reload=True)
