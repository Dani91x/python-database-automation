import os
from dotenv import load_dotenv

load_dotenv()

# =========================
# Core progetto (esistente)
# =========================
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
API_FOOTBALL_KEY = os.getenv("API_FOOTBALL_KEY")

# =========================
# Betfair (Italia - cert login)
# =========================
BETFAIR_APP_KEY = os.getenv("BETFAIR_APP_KEY")
BETFAIR_USERNAME = os.getenv("BETFAIR_USERNAME")
BETFAIR_PASSWORD = os.getenv("BETFAIR_PASSWORD")

# Percorsi file certificati (Windows ok; meglio con / oppure \\ nel .env)
BETFAIR_CERT_FILE = os.getenv("BETFAIR_CERT_FILE")
BETFAIR_KEY_FILE = os.getenv("BETFAIR_KEY_FILE")

# Endpoint login cert per Italia (da tua indicazione)
BETFAIR_IDENTITY_URL = os.getenv(
    "BETFAIR_IDENTITY_URL",
    "https://identitysso-cert.betfair.it/api/certlogin"
)

def _mask(value: str | None, left: int = 3, right: int = 2) -> str:
    """
    Maschera i segreti in log: mostra solo primi/ultimi caratteri.
    """
    if not value:
        return ""
    s = str(value)
    if len(s) <= left + right:
        return "*" * len(s)
    return f"{s[:left]}{'*' * (len(s) - left - right)}{s[-right:]}"

def print_loaded_config():
    print("SUPABASE_URL:", SUPABASE_URL)
    print("SUPABASE_SERVICE_ROLE_KEY presente:", bool(SUPABASE_SERVICE_ROLE_KEY))
    print("API_FOOTBALL_KEY presente:", bool(API_FOOTBALL_KEY))

    print("BETFAIR_APP_KEY presente:", bool(BETFAIR_APP_KEY), "|", _mask(BETFAIR_APP_KEY))
    print("BETFAIR_USERNAME presente:", bool(BETFAIR_USERNAME), "|", _mask(BETFAIR_USERNAME))
    print("BETFAIR_PASSWORD presente:", bool(BETFAIR_PASSWORD))  # NON stampare mai la password
    print("BETFAIR_CERT_FILE presente:", bool(BETFAIR_CERT_FILE), "|", BETFAIR_CERT_FILE)
    print("BETFAIR_KEY_FILE presente:", bool(BETFAIR_KEY_FILE), "|", BETFAIR_KEY_FILE)
    print("BETFAIR_IDENTITY_URL:", BETFAIR_IDENTITY_URL)
