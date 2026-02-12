from db_client import get_supabase_client

def check_table():
    sb = get_supabase_client()
    try:
        # Tenta una select sulla tabella leads
        resp = sb.table("leads").select("*").limit(1).execute()
        print(f"STATUS: Success")
        print(f"DATA: {resp.data}")
    except Exception as e:
        print(f"STATUS: Error")
        print(f"ERROR: {str(e)}")

if __name__ == "__main__":
    check_table()
