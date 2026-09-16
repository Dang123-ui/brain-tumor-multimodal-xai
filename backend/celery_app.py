import os
import sys
from pathlib import Path

from celery import Celery
from dotenv import load_dotenv

CURRENT_DIR = os.path.dirname(__file__)
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

# Local workers are usually started from backend/, while the shared .env lives
# at the repository root. Load it before Celery imports task modules, otherwise
# database.py falls back to the Docker-only host name "db".
load_dotenv(Path(CURRENT_DIR).resolve().parent / ".env", override=False)


CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", CELERY_BROKER_URL)


celery_app = Celery(
    "neuro_tasks",
    broker=CELERY_BROKER_URL,
    backend=CELERY_RESULT_BACKEND,
    include=["task"],
)
