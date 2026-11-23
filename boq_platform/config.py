from pathlib import Path
import os

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", "3306")),
    "user": os.getenv("DB_USER", "root"),
    "password": os.getenv("DB_PASSWORD", ""),
    "database": os.getenv("DB_NAME", "boq_intelligence"),
    "autocommit": False,
}
if os.getenv("DB_SSL_CA"):
    DB_CONFIG["ssl_ca"] = os.getenv("DB_SSL_CA")

MOC_API_BASE = os.getenv(
    "MOC_API_BASE", "https://dataapi.moc.go.th/csi-indexes"
)
LOG_DIR = ROOT / os.getenv("LOG_DIR", "logs")
RAW_DIR = ROOT / "data_raw"
EXPORT_DIR = ROOT / "exports"
RETAIL_MAX_AGE_DAYS = int(os.getenv("RETAIL_MAX_AGE_DAYS", "90"))

RETAIL_SOURCES = {
    "thai watsadu": "Thai Watsadu",
    "thaiwatsadu": "Thai Watsadu",
    "homepro": "HomePro",
    "dohome": "DoHome",
    "global house": "Global House",
    "globalhouse": "Global House",
    "hiachet": "Hiachet",
}
