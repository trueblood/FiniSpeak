"""Grant the FiniSpeak administrator role to an existing Firebase user.

Usage:
    python -m scripts.grant_admin person@example.com

The script uses the same FIREBASE_CREDENTIALS and FIREBASE_PROJECT_ID settings
as the web application. The user must sign out and back in to refresh the ID
token after the claim is changed.
"""

import argparse

from firebase_admin import auth

from services.firebase_service import get_db


def grant_admin(email):
    get_db()  # Initialize Firebase Admin before using the Auth client.
    user = auth.get_user_by_email(email.strip().lower())
    claims = dict(user.custom_claims or {})
    claims["admin"] = True
    auth.set_custom_user_claims(user.uid, claims)
    get_db().collection("users").document(user.uid).set(
        {"role": "admin", "status": "active", "email": user.email},
        merge=True,
    )
    return user


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Grant a FiniSpeak user administrator access.")
    parser.add_argument("email", help="Email address of an existing Firebase Authentication user")
    args = parser.parse_args()
    account = grant_admin(args.email)
    print(f"Administrator access granted to {account.email} ({account.uid}).")
    print("Have the user sign out and back in before opening the admin dashboard.")
