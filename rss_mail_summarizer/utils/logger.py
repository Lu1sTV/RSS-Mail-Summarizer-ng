# Imports
import os
import logging
from dotenv import load_dotenv

load_dotenv()

# Log-Level aus .env, Standard = INFO
log_level = os.getenv("LOG_LEVEL", "INFO").upper()

# Logging-Konfiguration
logging.basicConfig(
    level=getattr(logging, log_level, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

# Hauptlogger für alle Module
logger = logging.getLogger("app_logger")