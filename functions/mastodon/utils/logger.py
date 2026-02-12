"""
logger.py

Initialisiert den zentralen Logger für das Projekt.
Liest LOG_LEVEL aus der .env und konfiguriert das Logging-Format.
Stellt einen gemeinsamen Logger bereit, der in allen Modulen genutzt werden kann.
"""

# Imports
import os
import logging
from dotenv import load_dotenv

load_dotenv()

# Log-Level aus .env, Standard = INFO
log_level = os.getenv("LOG_LEVEL", "INFO").upper()

logging.basicConfig(
    level=getattr(logging, log_level, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

# Hauptlogger für alle Module
logger = logging.getLogger("app_logger")