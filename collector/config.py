"""Load collector settings without exposing credentials."""
from pathlib import Path
from dotenv import load_dotenv


def load_settings():
    # Explicit path works even when uvicorn starts from a different directory.
    # Shell settings take precedence over the project-local file.
    load_dotenv(Path(__file__).resolve().parent.parent / '.env', override=False)
