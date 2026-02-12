from api_client import APIFootballClient

def test_api_client():
    client = APIFootballClient()
    data = client.get_leagues()

    if not data:
        print("❌ Errore: nessun dato ricevuto dal client robusto")
    else:
        print("✅ Client robusto OK. Leagues ricevute:", data.get("results", "non trovato"))
        example = (data.get("response") or [None])[0]
        print("Esempio prima lega:", example)

if __name__ == "__main__":
    test_api_client()
