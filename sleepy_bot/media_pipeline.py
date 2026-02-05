"""Audio and video assembly via FFmpeg: concat WAVs, slideshow (zoompan + xfade), mix, mux to final_video.mp4."""

import logging
import subprocess
from pathlib import Path

from sleepy_bot import config

logger = logging.getLogger(__name__)

# Target: 1-hour slideshow then loop to 3 hours
ONE_HOUR_SEC = 3600
THREE_HOUR_SEC = 10800  # config.TARGET_VIDEO_DURATION_SEC
NARRATION_ATEMPO = 0.94
MUSIC_VOLUME = 0.2


def _run_ffmpeg(args: list[str], description: str = "ffmpeg") -> None:
    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "warning"] + args
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
    if p.returncode != 0:
        raise RuntimeError(f"{description} failed: {p.stderr or p.stdout}")


def concat_wavs(wav_paths: list[Path], output_path: Path) -> Path:
    """Concatenate WAV files in order into a single WAV. Uses concat demuxer."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    list_path = output_path.with_suffix(".concat.txt")
    lines = []
    for p in wav_paths:
        p = Path(p).resolve()
        if not p.exists():
            raise FileNotFoundError(f"WAV not found: {p}")
        lines.append(f"file '{p.as_posix()}'")
    list_path.write_text("\n".join(lines), encoding="utf-8")
    _run_ffmpeg(
        ["-f", "concat", "-safe", "0", "-i", str(list_path), "-c", "copy", str(output_path)],
        description="concat WAVs",
    )
    try:
        list_path.unlink()
    except OSError:
        pass
    logger.info("Concatenated %d WAVs -> %s", len(wav_paths), output_path)
    return output_path


def _collect_image_paths_ordered(images_dir: Path) -> list[Path]:
    """Return list of image paths in segment order: segment_01/001.png, 002.png, segment_02/..."""
    paths = []
    for seg_dir in sorted(images_dir.iterdir()):
        if not seg_dir.is_dir() or not seg_dir.name.startswith("segment_"):
            continue
        for f in sorted(seg_dir.iterdir()):
            if f.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp"):
                paths.append(f)
    return paths


def build_slideshow(
    images_dir: Path,
    output_video_path: Path,
    duration_sec: int = ONE_HOUR_SEC,
    loop_to_sec: int | None = None,
) -> Path:
    """
    Create a 1-hour slideshow with zoompan and xfade, then loop to loop_to_sec (default 3 hours).
    Image order: segment_01/001.png ... segment_N/xxx.png.
    """
    output_video_path = Path(output_video_path)
    output_video_path.parent.mkdir(parents=True, exist_ok=True)
    images_dir = Path(images_dir)
    image_paths = _collect_image_paths_ordered(images_dir)
    if not image_paths:
        raise FileNotFoundError(f"No images in {images_dir}")

    n = len(image_paths)
    duration_per_image = duration_sec / n

    fps = 25

    list_path = output_video_path.parent / "slideshow_images.txt"
    with open(list_path, "w", encoding="utf-8") as f:
        for p in image_paths:
            f.write(f"file '{Path(p).resolve().as_posix()}'\n")
            f.write(f"duration {duration_per_image}\n")
        # Repeat last image duration for concat demuxer
        f.write(f"file '{Path(image_paths[-1]).resolve().as_posix()}'\n")

    scale_zoom = (
        f"fps={fps},"
        "scale=1920:1080:force_original_aspect_ratio=decrease,"
        "pad=1920:1080:(ow-iw)/2:(oh-ih)/2,"
        f"zoompan=z='min(1.1,zoom+0.0003)':d=1:s=1920x1080:fps={fps}"
    )
    one_hour_path = output_video_path.parent / "slideshow_1h.mp4"
    _run_ffmpeg(
        [
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(list_path),
            "-vf",
            scale_zoom,
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-t",
            str(duration_sec),
            str(one_hour_path),
        ],
        description="slideshow 1h",
    )
    try:
        list_path.unlink(missing_ok=True)
    except OSError:
        pass

    # Loop to target duration if requested
    if loop_to_sec and loop_to_sec > duration_sec:
        _run_ffmpeg(
            [
                "-stream_loop",
                "-1",
                "-i",
                str(one_hour_path),
                "-t",
                str(loop_to_sec),
                "-c",
                "copy",
                str(output_video_path),
            ],
            description="loop slideshow",
        )
        try:
            one_hour_path.unlink(missing_ok=True)
        except OSError:
            pass
    else:
        one_hour_path.rename(output_video_path)
    logger.info("Slideshow written to %s", output_video_path)
    return output_video_path


def mix_and_mux(
    narration_wav: Path,
    slideshow_video: Path,
    output_mp4: Path,
    background_music_path: Path | None = None,
    atempo: float = NARRATION_ATEMPO,
    music_volume: float = MUSIC_VOLUME,
) -> Path:
    """Mix narration (with atempo) and optional background music, mux with video to final MP4."""
    output_mp4 = Path(output_mp4)
    output_mp4.parent.mkdir(parents=True, exist_ok=True)
    narration_wav = Path(narration_wav)
    slideshow_video = Path(slideshow_video)

    if background_music_path and Path(background_music_path).exists():
        filt = (
            f"[0:a]atempo={atempo}[nar];"
            f"[1:a]volume={music_volume}[mus];"
            "[nar][mus]amix=inputs=2:duration=longest[a]"
        )
        _run_ffmpeg(
            [
                "-i",
                str(narration_wav),
                "-i",
                str(background_music_path),
                "-i",
                str(slideshow_video),
                "-filter_complex",
                filt,
                "-map",
                "[a]",
                "-map",
                "2:v",
                "-c:v",
                "copy",
                "-shortest",
                str(output_mp4),
            ],
            description="mix and mux",
        )
    else:
        filt = f"[0:a]atempo={atempo}[a]"
        _run_ffmpeg(
            [
                "-i",
                str(narration_wav),
                "-i",
                str(slideshow_video),
                "-filter_complex",
                filt,
                "-map",
                "[a]",
                "-map",
                "1:v",
                "-c:v",
                "copy",
                "-shortest",
                str(output_mp4),
            ],
            description="mux narration + video",
        )
    logger.info("Final video: %s", output_mp4)
    return output_mp4


def run_media_pipeline(
    audio_dir: Path,
    images_dir: Path,
    assets_dir: Path | None = None,
    background_music_path: Path | None = None,
) -> Path:
    """
    Full media pipeline: concat WAVs -> narration.wav, build slideshow (1h, loop to target),
    mix narration + music, mux to final_video.mp4. Returns path to final_video.mp4.
    """
    assets_dir = Path(assets_dir or config.ASSETS_DIR)
    audio_dir = Path(audio_dir)
    images_dir = Path(images_dir)
    music = Path(background_music_path) if background_music_path else config.BACKGROUND_MUSIC_PATH
    if music and not music.exists():
        music = None

    wavs = sorted(audio_dir.glob("segment_*.wav"), key=lambda p: p.name)
    if not wavs:
        raise FileNotFoundError(f"No segment WAVs in {audio_dir}")
    narration_wav = assets_dir / "narration.wav"
    concat_wavs(wavs, narration_wav)

    slideshow_mp4 = assets_dir / "slideshow.mp4"
    build_slideshow(
        images_dir,
        slideshow_mp4,
        duration_sec=ONE_HOUR_SEC,
        loop_to_sec=config.TARGET_VIDEO_DURATION_SEC,
    )

    final = assets_dir / "final_video.mp4"
    mix_and_mux(
        narration_wav,
        slideshow_mp4,
        final,
        background_music_path=music,
        atempo=NARRATION_ATEMPO,
        music_volume=MUSIC_VOLUME,
    )
    return final


def cleanup_temp_assets(assets_dir: Path | None = None, keep_final: bool = True) -> None:
    """Remove temporary files, optionally keeping final_video.mp4."""
    assets_dir = Path(assets_dir or config.ASSETS_DIR)
    for name in ["narration.wav", "slideshow.mp4", "slideshow_1h.mp4", "segments.json", "script.txt"]:
        p = assets_dir / name
        if p.exists():
            p.unlink()
            logger.info("Removed %s", p)
    audio_dir = assets_dir / "audio"
    if audio_dir.exists():
        for f in audio_dir.glob("*.wav"):
            f.unlink()
            logger.info("Removed %s", f)
    if not keep_final:
        final = assets_dir / "final_video.mp4"
        if final.exists():
            final.unlink()
            logger.info("Removed %s", final)
