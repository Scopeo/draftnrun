import argparse

from settings import settings
from supabase import Client, create_client


def get_user_jwt(username: str, password: str) -> str:
    """
    Authenticate a user and retrieve their JWT.

    Args:
        username (str): The user's email or username.
        password (str): The user's password.

    Returns:
        str: The user's JWT token.
    """
    supabase: Client = create_client(
        settings.SUPABASE_PROJECT_URL,
        settings.SUPABASE_PROJECT_KEY,
    )

    try:
        response = supabase.auth.sign_in_with_password({
            "email": username,
            "password": password,
        })

        if hasattr(response, "session") and response.session:
            return response.session.access_token

        raise ValueError("Failed to retrieve JWT. Check your credentials.")
    except Exception as e:
        print(f"Error: {e}")
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Authenticate a user and retrieve their JWT.")
    parser.add_argument("--username", required=True, help="The user's email or username")
    parser.add_argument("--password", required=True, help="The user's password")
    args = parser.parse_args()

    try:
        jwt = get_user_jwt(args.username, args.password)
        print(jwt)
    except Exception as e:
        print("Authentication failed.")
        raise e
