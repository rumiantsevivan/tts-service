"""FastAPI server for TTS service."""

import os
import uuid
import asyncio
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from document_parser import extract_text, SUPPORTED_EXTENSIONS
from tts_engine import text_to_speech, get_available_voices

app = FastAPI(title="TTS Service", description="Convert documents to speech")

UPLOAD_DIR = Path(__file__).parent / "uploads"
OUTPUT_DIR = Path(__file__).parent / "outputs"
UPLOAD_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)

# In-memory job storage
jobs: dict[str, dict] = {}


@app.post("/upload")
async def upload_file(file: UploadFile = File(...), voice: Optional[str] = None):
    """Upload a document and start TTS generation."""
    ext = Path(file.filename).suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported format: {ext}. Supported: {', '.join(SUPPORTED_EXTENSIONS)}",
        )

    job_id = str(uuid.uuid4())

    # Save uploaded file
    upload_path = UPLOAD_DIR / f"{job_id}{ext}"
    content = await file.read()
    upload_path.write_bytes(content)

    # Initialize job
    jobs[job_id] = {
        "status": "processing",
        "progress": 0,
        "total_chunks": 0,
        "stage": "Extracting text...",
        "filename": file.filename,
        "output_path": None,
        "error": None,
    }

    # Run TTS in background
    asyncio.get_event_loop().run_in_executor(
        None, _process_job, job_id, str(upload_path), voice
    )

    return {"job_id": job_id}


def _process_job(job_id: str, filepath: str, voice: Optional[str]):
    """Process a TTS job (runs in thread pool)."""
    try:
        # Extract text
        jobs[job_id]["stage"] = "Extracting text..."
        text = extract_text(filepath)

        if not text.strip():
            jobs[job_id]["status"] = "error"
            jobs[job_id]["error"] = "No text found in document"
            return

        # Generate audio
        jobs[job_id]["stage"] = "Generating audio..."
        output_path = str(OUTPUT_DIR / f"{job_id}.mp3")

        def on_progress(current, total):
            jobs[job_id]["progress"] = current
            jobs[job_id]["total_chunks"] = total
            jobs[job_id]["stage"] = f"Generating audio... ({current}/{total} chunks)"

        text_to_speech(
            text=text,
            output_path=output_path,
            voice=voice or "ru_RU-irina-medium",
            on_progress=on_progress,
        )

        jobs[job_id]["status"] = "completed"
        jobs[job_id]["output_path"] = output_path
        jobs[job_id]["stage"] = "Done!"

    except Exception as e:
        jobs[job_id]["status"] = "error"
        jobs[job_id]["error"] = str(e)

    finally:
        # Clean up uploaded file
        try:
            os.remove(filepath)
        except OSError:
            pass


@app.get("/status/{job_id}")
async def get_status(job_id: str):
    """Get the status of a TTS job."""
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")

    job = jobs[job_id]
    return {
        "job_id": job_id,
        "status": job["status"],
        "progress": job["progress"],
        "total_chunks": job["total_chunks"],
        "stage": job["stage"],
        "filename": job["filename"],
        "error": job["error"],
    }


@app.get("/download/{job_id}")
async def download_file(job_id: str):
    """Download the generated MP3 file."""
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")

    job = jobs[job_id]
    if job["status"] != "completed":
        raise HTTPException(status_code=400, detail=f"Job is not ready: {job['status']}")

    output_path = job["output_path"]
    if not output_path or not os.path.exists(output_path):
        raise HTTPException(status_code=404, detail="Output file not found")

    # Use original filename with .mp3 extension
    download_name = Path(job["filename"]).stem + ".mp3"
    return FileResponse(output_path, filename=download_name, media_type="audio/mpeg")


@app.get("/voices")
async def list_voices():
    """List available TTS voices."""
    return get_available_voices()


# Mount static files (frontend) — must be last
app.mount("/", StaticFiles(directory="static", html=True), name="static")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
