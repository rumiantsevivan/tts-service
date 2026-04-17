"""TTS engine: splits text into chunks, generates audio via Edge TTS, concatenates with ffmpeg."""

import asyncio
import os
import re
import subprocess
import tempfile
from typing import Callable, Optional

import edge_tts

# Available Russian voices
VOICES = [
    {"id": "ru-RU-SvetlanaNeural", "name": "Svetlana (female)"},
    {"id": "ru-RU-DmitryNeural", "name": "Dmitry (male)"},
]
DEFAULT_VOICE = "ru-RU-SvetlanaNeural"

# Chunking settings
MAX_CHUNK_CHARS = 4000


def get_available_voices() -> list[dict]:
    """Return list of available TTS voices."""
    return VOICES


def split_into_chunks(text: str, max_chars: int = MAX_CHUNK_CHARS) -> list[str]:
    """Split text into chunks at sentence boundaries, respecting max_chars limit."""
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


async def _generate_chunk(text: str, voice: str, output_path: str):
    """Generate a single MP3 chunk using Edge TTS."""
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(output_path)


def text_to_speech(
    text: str,
    output_path: str,
    voice: str = DEFAULT_VOICE,
    on_progress: Optional[Callable[[int, int], None]] = None,
) -> str:
    """
    Convert text to MP3 file.

    Args:
        text: Input text to synthesize.
        output_path: Path where the final MP3 will be saved.
        voice: Edge TTS voice name (e.g. ru-RU-SvetlanaNeural).
        on_progress: Callback(current_chunk, total_chunks) for progress tracking.

    Returns:
        Path to the generated MP3 file.
    """
    chunks = split_into_chunks(text)
    total = len(chunks)

    if total == 0:
        raise ValueError("No text to synthesize")

    # Single chunk — generate directly to output
    if total == 1:
        asyncio.run(_generate_chunk(chunks[0], voice, output_path))
        if on_progress:
            on_progress(1, 1)
        return output_path

    # Multiple chunks — generate individually, then concatenate with ffmpeg
    with tempfile.TemporaryDirectory() as tmpdir:
        mp3_files = []

        for i, chunk in enumerate(chunks):
            chunk_path = os.path.join(tmpdir, f"chunk_{i:05d}.mp3")
            asyncio.run(_generate_chunk(chunk, voice, chunk_path))
            mp3_files.append(chunk_path)

            if on_progress:
                on_progress(i + 1, total)

        # Build ffmpeg concat list
        concat_list_path = os.path.join(tmpdir, "concat.txt")
        with open(concat_list_path, "w", encoding="utf-8") as f:
            for mp3_path in mp3_files:
                # Escape single quotes for ffmpeg
                safe_path = mp3_path.replace("'", "'\\''")
                f.write(f"file '{safe_path}'\n")

        # Concatenate all MP3 files
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        result = subprocess.run(
            [
                "ffmpeg", "-y", "-f", "concat", "-safe", "0",
                "-i", concat_list_path, "-c", "copy", output_path,
            ],
            capture_output=True,
            timeout=300,
        )

        if result.returncode != 0:
            raise RuntimeError(f"ffmpeg concatenation failed: {result.stderr.decode()}")

    return output_path
