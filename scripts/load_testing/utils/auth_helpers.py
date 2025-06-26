"""Authentication helpers for load testing"""

from typing import Dict

try:
    from ada_backend.scripts.get_supabase_token import get_user_jwt
    from settings import settings
except ImportError as e:
    print(f"Warning: Could not import auth modules: {e}")
    print(
        "Make sure you're running with 'uv run python -m scripts.load_testing.utils.auth_helpers' from the project root"
    )

# Test constants - update these for your environment
TEST_ORGANIZATION_ID = "37b7d67f-8f29-4fce-8085-19dea582f605"
TEST_PROJECT_ID = "f7ddbfcb-6843-4ae9-a15b-40aa565b955b"


def get_test_jwt_token() -> str:
    """Get JWT token for testing"""
    try:
        # Use the same test credentials as the test suite
        test_email = getattr(settings, "TEST_USER_EMAIL", None)
        test_password = getattr(settings, "TEST_USER_PASSWORD", None)

        if not test_email or not test_password:
            raise Exception(
                "TEST_USER_EMAIL and TEST_USER_PASSWORD must be set in settings. " "Check your credentials.env file."
            )

        token = get_user_jwt(test_email, test_password)
        return token

    except Exception as e:
        print(f"Failed to get JWT token: {e}")
        print("Suggestions:")
        print("1. Make sure your Supabase credentials are correct in credentials.env")
        print("2. Verify TEST_USER_EMAIL and TEST_USER_PASSWORD are set")
        print("3. Ensure the test user exists in your Supabase instance")
        raise


def get_api_key_headers() -> Dict[str, str]:
    """Get API key headers for ingestion endpoints"""
    try:
        api_key = getattr(settings, "INGESTION_API_KEY", None)
        if not api_key:
            raise Exception("INGESTION_API_KEY not found in settings")

        return {"x-ingestion-api-key": api_key, "Content-Type": "application/json"}
    except Exception as e:
        print(f"Failed to get API key headers: {e}")
        raise


def validate_auth_setup() -> bool:
    """Validate that authentication is properly configured"""
    try:
        token = get_test_jwt_token()
        if token and len(token) > 0:
            print("✅ JWT authentication configured correctly")
            return True
        else:
            print("❌ JWT token is empty")
            return False
    except Exception as e:
        print(f"❌ Auth validation failed: {e}")
        return False


if __name__ == "__main__":
    """Test the authentication setup"""
    print("Testing authentication setup...")

    if validate_auth_setup():
        print("🎉 Authentication is ready for load testing!")
        print(f"Organization ID: {TEST_ORGANIZATION_ID}")
        print(f"Project ID: {TEST_PROJECT_ID}")
    else:
        print("❌ Authentication setup needs attention")
        sys.exit(1)
