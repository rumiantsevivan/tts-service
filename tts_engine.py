"""TTS engine: splits text into chunks, generates audio via Piper, concatenates with ffmpeg."""

import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Callable, Optional

# Path to Piper executable (relative to project root)
PIPER_DIR = Path(__file__).parent / "piper" / "piper"
PIPER_EXE = PIPER_DIR / "piper.exe"
DEFAULT_MODEL = "ru_RU-irina-medium"

# Chunking settings
MAX_CHUNK_CHARS = 4000
SILENCE_BETWEEN_CHUNKS_MS = 300


def get_available_voices() -> list[dict]:
    """Return list of available voice models."""
    voices = []
    for f in PIPER_DIR.glob("*.onnx"):
        if f.suffix == ".onnx" and not f.name.endswith(".json"):
            name = f.stem
            voices.append({"id": name, "name": name.replace("-", " ").replace("_", " ")})
    return voices or [{"id": DEFAULT_MODEL, "name": "Irina (Russian, medium)"}]


def split_into_chunks(text: str, max_chars: int = MAX_CHUNK_CHARS) -> list[str]:
    """Split text into chunks at sentence boundaries, respecting max_chars limit."""
    # Split by sentence-ending punctuation (keeping the punctuation)
    sentences = re.split(r"(?<=[.!?])\s+", text)

    chunks = []
    current_chunk = ""

    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue

        # If a single sentence exceeds max_chars, split it further at commas/semicolons
        if len(sentence) > max_chars:
            sub_parts = re.split(r"(?<=[,;:])\s+", sentence)
            for part in sub_parts:
                if len(current_chunk) + len(part) + 1 > max_chars and current_chunk:
                    chunks.append(current_chunk.strip())
                    current_chunk = ""
                current_chunk += " " + part
            continue

        if len(current_chunk) + len(sentence) + 1 > max_chars and current_chunk:
            chunks.append(current_chunk.strip())
            current_chunk = ""

        current_chunk += " " + sentence

    if current_chunk.strip():
        chunks.append(current_chunk.strip())

    return chunks


def text_to_speech(
    text: str,
    output_path: str,
    voice: str = DEFAULT_MODEL,
    on_progress: Optional[Callable[[int, int], None]] = None,
) -> str:
    """
    Convert text to MP3 file.

    Args:
        text: Input text to synthesize.
        output_path: Path where the final MP3 will be saved.
        voice: Piper voice model name.
        on_progress: Callback(current_chunk, total_chunks) for progress tracking.

    Returns:
        Path to the generated MP3 file.
    """
    if not PIPER_EXE.exists():
        raise FileNotFoundError(f"Piper executable not found at {PIPER_EXE}")

    model_path = PIPER_DIR / f"{voice}.onnx"
    if not model_path.exists():
        raise FileNotFoundError(f"Voice model not found: {model_path}")

    chunks = split_into_chunks(text)
    total = len(chunks)

    if total == 0:
        raise ValueError("No text to synthesize")

    with tempfile.TemporaryDirectory() as tmpdir:
        wav_files = []

        for i, chunk in enumerate(chunks):
            wav_path = os.path.join(tmpdir, f"chunk_{i:05d}.wav")

            result = subprocess.run(
                [str(PIPER_EXE), "--model", str(model_path), "--output_file", wav_path],
                input=chunk.encode("utf-8"),
                capture_output=True,
                timeout=120,
            )

            if result.returncode != 0:
                raise RuntimeError(f"Piper failed on chunk {i}: {result.stderr.decode()}")

            wav_files.append(wav_path)

            if on_progress:
                on_progress(i + 1, total)

        # Generate silence file for gaps between chunks
        silence_path = os.path.join(tmpdir, "silence.wav")
        subprocess.run(
            [
                "ffmpeg", "-y", "-f", "lavfi", "-i",
                f"anullsrc=r=22050:cl=mono",
                "-t", str(SILENCE_BETWEEN_CHUNKS_MS / 1000),
                silence_path,
            ],
            capture_output=True,
            timeout=30,
        )

        # Build concat list (chunk + silence + chunk + silence + ...)
        concat_list_path = os.path.join(tmpdir, "concat.txt")
        with open(concat_list_path, "w") as f:
            for i, wav_path in enumerate(wav_files):
                f.write(f"file '{wav_path}'\n")
                if i < len(wav_files) - 1:
                    f.write(f"file '{silence_path}'\n")

        # Concatenate all WAV files
        combined_wav = os.path.join(tmpdir, "combined.wav")
        subprocess.run(
            [
                "ffmpeg", "-y", "-f", "concat", "-safe", "0",
                "-i", concat_list_path, "-c", "copy", combined_wav,
            ],
            capture_output=True,
            timeout=300,
        )

        # Convert to MP3
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        result = subprocess.run(
            [
                "ffmpeg", "-y", "-i", combined_wav,
                "-codec:a", "libmp3lame", "-qscale:a", "2",
                output_path,
            ],
            capture_output=True,
            timeout=300,
        )

        if result.returncode != 0:
            raise RuntimeError(f"ffmpeg MP3 conversion failed: {result.stderr.decode()}")

    return output_path
