from supabase import create_client
from dotenv import load_dotenv
import os

load_dotenv()

url = os.getenv("SUPABASE_URL")
key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

sb = create_client(url, key)

try:
    print("✅ Connessione a Supabase eseguita correttamente")
except Exception as e:
    print("❌ Errore di connessione:", e)
