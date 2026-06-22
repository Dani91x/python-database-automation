"""Reset (o crea) la password dell'owner via Supabase Admin API.

GARANZIA ANTI-BLOCCO: funziona SEMPRE, anche se l'email di reset non arriva,
perché usa la SERVICE_ROLE_KEY (privilegi admin) e non dipende dalla posta.

Uso:
    python admin_reset_password.py "nuova_password"
    python admin_reset_password.py "nuova_password" --email altra@email.com

Se l'utente non esiste viene creato (email gia' confermata).
"""
from __future__ import annotations

import argparse
import sys

import requests

from config import SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY

OWNER_EMAIL_DEFAULT = "daniele.ritrovato@gmail.com"


def _headers() -> dict[str, str]:
    if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
        sys.exit("ERRORE: SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY mancanti nel .env")
    return {
        "apikey": SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
        "Content-Type": "application/json",
    }


def _find_user_id(email: str) -> str | None:
    """Ritorna l'id dell'utente con quell'email, oppure None."""
    base = SUPABASE_URL.rstrip("/")
    resp = requests.get(
        f"{base}/auth/v1/admin/users",
        headers=_headers(),
        params={"per_page": 200},
        timeout=30,
    )
    resp.raise_for_status()
    users = resp.json().get("users", [])
    for user in users:
        if (user.get("email") or "").lower() == email.lower():
            return user["id"]
    return None


def reset_password(email: str, new_password: str) -> None:
    base = SUPABASE_URL.rstrip("/")
    user_id = _find_user_id(email)

    if user_id:
        resp = requests.put(
            f"{base}/auth/v1/admin/users/{user_id}",
            headers=_headers(),
            json={"password": new_password, "email_confirm": True},
            timeout=30,
        )
        resp.raise_for_status()
        print(f"OK: password aggiornata per {email} (id {user_id}).")
    else:
        resp = requests.post(
            f"{base}/auth/v1/admin/users",
            headers=_headers(),
            json={
                "email": email,
                "password": new_password,
                "email_confirm": True,
                "user_metadata": {"owner": True},
            },
            timeout=30,
        )
        resp.raise_for_status()
        print(f"OK: utente creato {email} (id {resp.json().get('id')}).")


def main() -> None:
    parser = argparse.ArgumentParser(description="Reset password owner via Admin API.")
    parser.add_argument("password", help="La nuova password (min. 6 caratteri).")
    parser.add_argument("--email", default=OWNER_EMAIL_DEFAULT, help="Email dell'utente.")
    args = parser.parse_args()

    if len(args.password) < 6:
        sys.exit("ERRORE: la password deve avere almeno 6 caratteri.")

    reset_password(args.email, args.password)


if __name__ == "__main__":
    main()
