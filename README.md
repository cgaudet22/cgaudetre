# SleepyServerBot One-File Workflow

This repository provides a single script, `workflow_one_file.py`, that runs the full pipeline:

1. Google Sheets input
2. DeepSeek script generation
3. Pollinations image generation
4. Inworld TTS generation
5. FFmpeg media assembly
6. Optional YouTube upload

## Usage

### 1) Install dependencies

```bash
pip install google-auth google-auth-oauthlib google-auth-httplib2 gspread google-api-python-client requests python-dotenv
```

### 2) Configure environment

Copy `.env.example` to `.env` and fill required values.

### 3) Run

```bash
python workflow_one_file.py --dry-run --short-run
python workflow_one_file.py
```

## Flags

- `--dry-run` / `--skip-upload`: run entire workflow except YouTube upload.
- `--short-run`: fewer segments/images for quicker validation.

## Requirements

- FFmpeg available on PATH.
- Valid credentials and API keys for configured integrations.
