"""YouTube upload via OAuth2 and resumable uploads. Returns video ID and optional URL for sheet update."""

import json
import logging
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

from sleepy_bot import config

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
YOUTUBE_API_SERVICE_NAME = "youtube"
YOUTUBE_API_VERSION = "v3"
RESUMABLE_CHUNK_SIZE = 1024 * 1024 * 4  # 4 MB


def _get_credentials() -> Credentials:
    """Load or create OAuth2 credentials using client secret and optional token file."""
    token_path = config.YOUTUBE_TOKEN_PATH
    client_path = config.YOUTUBE_CLIENT_SECRET_PATH
    if not client_path or not Path(client_path).exists():
        raise FileNotFoundError(
            f"YouTube client secret not found at {client_path}. Set YOUTUBE_CLIENT_SECRET_PATH."
        )
    creds = None
    if token_path and Path(token_path).exists():
        try:
            creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
        except Exception as e:
            logger.warning("Could not load token file: %s", e)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(str(client_path), SCOPES)
            creds = flow.run_local_server(port=0)
        if token_path:
            Path(token_path).parent.mkdir(parents=True, exist_ok=True)
            with open(token_path, "w") as f:
                f.write(creds.to_json())
    return creds


def upload_video(
    video_path: Path,
    title: str,
    description: str = "",
    category_id: str = "28",  # Science & Technology
    privacy: str = "private",
    tags: list[str] | None = None,
) -> tuple[str, str]:
    """
    Upload video to YouTube using resumable upload. Returns (video_id, video_url).
    """
    creds = _get_credentials()
    youtube = build(
        YOUTUBE_API_SERVICE_NAME,
        YOUTUBE_API_VERSION,
        credentials=creds,
    )
    body = {
        "snippet": {
            "title": title[:100],
            "description": description[:5000] if description else "",
            "tags": tags or [],
            "categoryId": category_id,
        },
        "status": {
            "privacyStatus": privacy,
            "selfDeclaredMadeForKids": False,
        },
    }
    media = MediaFileUpload(
        str(video_path),
        mimetype="video/mp4",
        resumable=True,
        chunksize=RESUMABLE_CHUNK_SIZE,
    )
    request = youtube.videos().insert(
        part="snippet,status",
        body=body,
        media_body=media,
    )
    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            logger.info("Upload progress: %d%%", int(status.progress() * 100))
    video_id = response["id"]
    url = f"https://www.youtube.com/watch?v={video_id}"
    logger.info("Uploaded: %s", url)
    return video_id, url


def upload_final_video(
    assets_dir: Path | None = None,
    title: str | None = None,
    description: str = "",
    topic: str = "",
) -> tuple[str, str]:
    """
    Upload assets_dir/final_video.mp4 to YouTube. Title defaults to "Sleepy Science: {topic}" or date.
    Returns (video_id, video_url).
    """
    assets_dir = Path(assets_dir or config.ASSETS_DIR)
    video_path = assets_dir / "final_video.mp4"
    if not video_path.exists():
        raise FileNotFoundError(f"Final video not found: {video_path}")
    if not title:
        title = f"Sleepy Science: {topic}" if topic else "Sleepy Science"
    return upload_video(
        video_path,
        title=title,
        description=description or f"Topic: {topic}",
        category_id="28",
        privacy="private",
        tags=["sleep", "science", "education"] + ([topic] if topic else []),
    )
