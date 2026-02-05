#!/usr/bin/env python3
"""
SleepyServerBot one-file workflow.

Runs the full pipeline in a single script:
Sheets -> DeepSeek script generation -> Pollinations images -> Inworld TTS
-> FFmpeg media assembly -> optional YouTube upload + sheet update.

Quick start
-----------
1) Install dependencies once:
   pip install google-auth google-auth-oauthlib google-auth-httplib2 \
       gspread google-api-python-client requests python-dotenv

2) Configure environment variables (or create a .env beside this file).

3) Run:
   python workflow_one_file.py --dry-run --short-run   # test without upload
   python workflow_one_file.py                         # full run + upload

Flags:
- --dry-run / --skip-upload: run everything except YouTube upload.
- --short-run: fewer segments/images (same as SLEEPY_SHORT_RUN=1).

Requirements:
- FFmpeg on PATH
- Valid credentials and env vars for Sheets, DeepSeek, Inworld, and YouTube.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import shutil
import subprocess
import sys
import textwrap
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv

try:
    import gspread
except Exception:  # pragma: no cover - optional in dry testing envs
    gspread = None

try:
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
except Exception:  # pragma: no cover
    build = None
    MediaFileUpload = None

LOGGER = logging.getLogger("workflow")


@dataclass
class WorkflowConfig:
    output_dir: Path
    short_run: bool
    dry_run: bool
    # Sheets
    sheet_name: str
    worksheet_name: str
    # APIs
    deepseek_api_key: str
    inworld_api_key: str
    inworld_voice_id: str
    # upload
    youtube_privacy_status: str


def env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def get_config(args: argparse.Namespace) -> WorkflowConfig:
    short_run = bool(args.short_run or env("SLEEPY_SHORT_RUN", "0") == "1")
    dry_run = bool(args.dry_run or args.skip_upload)
    output_dir = Path(env("SLEEPY_OUTPUT_DIR", "outputs")).resolve()
    return WorkflowConfig(
        output_dir=output_dir,
        short_run=short_run,
        dry_run=dry_run,
        sheet_name=env("SLEEPY_SHEET_NAME"),
        worksheet_name=env("SLEEPY_WORKSHEET_NAME", "Queue"),
        deepseek_api_key=env("DEEPSEEK_API_KEY"),
        inworld_api_key=env("INWORLD_API_KEY"),
        inworld_voice_id=env("INWORLD_VOICE_ID"),
        youtube_privacy_status=env("YOUTUBE_PRIVACY_STATUS", "private"),
    )


def assert_prereqs() -> None:
    if shutil.which("ffmpeg") is None:
        raise RuntimeError("FFmpeg is not on PATH.")


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def read_sheet_prompt(cfg: WorkflowConfig) -> dict[str, Any]:
    if not cfg.sheet_name:
        LOGGER.warning("SLEEPY_SHEET_NAME not set; using local fallback prompt")
        return {"title": "Dry run sample", "prompt": "A relaxing bedtime tech story."}

    if gspread is None:
        raise RuntimeError("gspread is unavailable; install dependencies first")

    cred_path = env("GOOGLE_APPLICATION_CREDENTIALS")
    if not cred_path:
        raise RuntimeError("GOOGLE_APPLICATION_CREDENTIALS is required for Sheets access")

    client = gspread.service_account(filename=cred_path)
    worksheet = client.open(cfg.sheet_name).worksheet(cfg.worksheet_name)
    row = worksheet.get_all_records(head=1)[0]
    LOGGER.info("Loaded prompt row from sheet: %s", row.get("title", "(untitled)"))
    return row


def deepseek_script(prompt: str, api_key: str, segment_count: int) -> list[str]:
    if not api_key:
        LOGGER.warning("DEEPSEEK_API_KEY missing; using deterministic fallback script")
        return [f"Segment {i+1}: {prompt}" for i in range(segment_count)]

    payload = {
        "model": env("DEEPSEEK_MODEL", "deepseek-chat"),
        "messages": [
            {
                "role": "system",
                "content": "Write soothing script segments for narrated sleep content.",
            },
            {
                "role": "user",
                "content": f"Create {segment_count} segments for: {prompt}. Return JSON array of strings.",
            },
        ],
        "temperature": 0.7,
    }
    resp = requests.post(
        env("DEEPSEEK_API_URL", "https://api.deepseek.com/chat/completions"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json=payload,
        timeout=120,
    )
    resp.raise_for_status()
    text = resp.json()["choices"][0]["message"]["content"]
    return json.loads(text)


def generate_images(segments: list[str], out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    image_paths: list[Path] = []
    size = env("POLLINATIONS_SIZE", "1280x720")
    for i, segment in enumerate(segments, 1):
        url = f"https://image.pollinations.ai/prompt/{requests.utils.quote(segment[:350])}?width={size.split('x')[0]}&height={size.split('x')[1]}"
        path = out_dir / f"image_{i:03d}.jpg"
        resp = requests.get(url, timeout=180)
        resp.raise_for_status()
        path.write_bytes(resp.content)
        image_paths.append(path)
        LOGGER.info("Generated image %s", path.name)
    return image_paths


def synthesize_tts(segments: list[str], cfg: WorkflowConfig, out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    audio_paths: list[Path] = []

    for i, text in enumerate(segments, 1):
        target = out_dir / f"audio_{i:03d}.mp3"
        if not cfg.inworld_api_key or not cfg.inworld_voice_id:
            # deterministic 8s silence fallback
            subprocess.run(
                [
                    "ffmpeg",
                    "-y",
                    "-f",
                    "lavfi",
                    "-i",
                    "anullsrc=r=44100:cl=stereo",
                    "-t",
                    "8",
                    str(target),
                ],
                check=True,
                capture_output=True,
            )
        else:
            resp = requests.post(
                env("INWORLD_TTS_URL", "https://api.inworld.ai/tts"),
                headers={"Authorization": f"Bearer {cfg.inworld_api_key}", "Content-Type": "application/json"},
                json={"text": text, "voiceId": cfg.inworld_voice_id, "format": "mp3"},
                timeout=120,
            )
            resp.raise_for_status()
            target.write_bytes(resp.content)
        audio_paths.append(target)
        LOGGER.info("Generated audio %s", target.name)
    return audio_paths


def mux_media(images: list[Path], audios: list[Path], out_file: Path) -> None:
    if len(images) != len(audios):
        raise ValueError("Image and audio counts must match")

    tmp = out_file.parent
    list_path = tmp / "segments.txt"
    parts: list[str] = []

    for i, (image, audio) in enumerate(zip(images, audios), 1):
        part = tmp / f"part_{i:03d}.mp4"
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-loop",
                "1",
                "-i",
                str(image),
                "-i",
                str(audio),
                "-c:v",
                "libx264",
                "-tune",
                "stillimage",
                "-c:a",
                "aac",
                "-b:a",
                "192k",
                "-shortest",
                "-pix_fmt",
                "yuv420p",
                str(part),
            ],
            check=True,
            capture_output=True,
        )
        parts.append(f"file '{part.as_posix()}'")

    list_path.write_text("\n".join(parts) + "\n", encoding="utf-8")
    subprocess.run(
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(list_path), "-c", "copy", str(out_file)],
        check=True,
        capture_output=True,
    )


def upload_youtube(video: Path, title: str, description: str, cfg: WorkflowConfig) -> str:
    if build is None or MediaFileUpload is None:
        raise RuntimeError("google-api-python-client unavailable for upload")

    cred_path = env("GOOGLE_APPLICATION_CREDENTIALS")
    if not cred_path:
        raise RuntimeError("GOOGLE_APPLICATION_CREDENTIALS is required for YouTube upload")

    from google.oauth2 import service_account

    creds = service_account.Credentials.from_service_account_file(
        cred_path,
        scopes=["https://www.googleapis.com/auth/youtube.upload"],
    )
    yt = build("youtube", "v3", credentials=creds)

    request = yt.videos().insert(
        part="snippet,status",
        body={
            "snippet": {"title": title, "description": description},
            "status": {"privacyStatus": cfg.youtube_privacy_status},
        },
        media_body=MediaFileUpload(str(video), resumable=True),
    )
    response = request.execute()
    return response["id"]


def run(args: argparse.Namespace) -> int:
    load_dotenv()
    setup_logging()
    assert_prereqs()

    cfg = get_config(args)
    cfg.output_dir.mkdir(parents=True, exist_ok=True)

    source = read_sheet_prompt(cfg)
    title = source.get("title", "Untitled Sleep Story")
    prompt = source.get("prompt", title)
    segment_count = 2 if cfg.short_run else int(env("SLEEPY_SEGMENT_COUNT", "6"))

    segments = deepseek_script(prompt=prompt, api_key=cfg.deepseek_api_key, segment_count=segment_count)
    images = generate_images(segments, cfg.output_dir / "images")
    audios = synthesize_tts(segments, cfg, cfg.output_dir / "audio")

    video_path = cfg.output_dir / "final_video.mp4"
    mux_media(images, audios, video_path)
    LOGGER.info("Built video: %s", video_path)

    if cfg.dry_run:
        LOGGER.info("Dry run enabled; skipping upload.")
        return 0

    video_id = upload_youtube(video_path, title=title, description=prompt, cfg=cfg)
    LOGGER.info("Uploaded to YouTube video id=%s", video_id)
    return 0


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Run SleepyServerBot one-file workflow")
    p.add_argument("--dry-run", action="store_true", help="Run pipeline but skip YouTube upload")
    p.add_argument("--skip-upload", action="store_true", help="Alias for --dry-run")
    p.add_argument("--short-run", action="store_true", help="Use fewer segments and images")
    return p.parse_args(argv)


if __name__ == "__main__":
    try:
        raise SystemExit(run(parse_args(sys.argv[1:])))
    except Exception as exc:  # intentionally top-level for CLI visibility
        msg = textwrap.shorten(str(exc), width=600, placeholder="...")
        LOGGER.error("Workflow failed: %s", msg)
        raise
