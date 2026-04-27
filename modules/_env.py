"""Charge le .env depuis le répertoire racine du projet, peu importe le cwd."""
import os
from pathlib import Path
from dotenv import load_dotenv

_ROOT = Path(__file__).parent.parent  # insolit-studio/
load_dotenv(dotenv_path=_ROOT / ".env", override=True)
