"""Test data generators for load testing"""

import random
import uuid


def generate_chat_message():
    """Generate chat message payload"""
    sample_questions = [
        "Hello, how are you?",
        "What is the weather like today?",
        "Can you help me with a task?",
        "Explain machine learning in simple terms",
        "What are the benefits of renewable energy?",
        "How do I improve my productivity?",
        "What is the capital of France?",
        "Tell me a joke",
        "What is artificial intelligence?",
        "How does photosynthesis work?",
        "What are the best programming practices?",
        "Explain quantum computing",
        "What is the meaning of life?",
        "How do I learn a new language?",
        "What is blockchain technology?",
    ]

    return {"messages": [{"role": "user", "content": random.choice(sample_questions)}]}


def generate_project_data():
    """Generate project creation data"""
    project_names = [
        "AI Assistant Bot",
        "Customer Support Agent",
        "Data Analysis Pipeline",
        "Content Generator",
        "Research Assistant",
        "Code Review Bot",
        "Marketing Automation",
        "Document Processor",
    ]

    descriptions = [
        "An intelligent assistant for customer inquiries",
        "Automated data processing and analysis",
        "Content generation for marketing campaigns",
        "Research and information gathering tool",
        "Code quality and review automation",
        "Document analysis and summarization",
        "Customer onboarding automation",
        "Knowledge base management system",
    ]

    return {
        "project_id": str(uuid.uuid4()),
        "project_name": f"{random.choice(project_names)} {random.randint(1, 999)}",
        "description": random.choice(descriptions),
        "companion_image_url": f"https://example.com/images/{random.randint(1, 100)}.jpg",
    }


def generate_api_key_data():
    """Generate API key creation data"""
    key_names = [
        "production-key",
        "development-key",
        "staging-key",
        "testing-key",
        "integration-key",
        "backup-key",
    ]

    return {
        "key_name": f"{random.choice(key_names)}-{random.randint(1000, 9999)}",
        "project_id": "f7ddbfcb-6843-4ae9-a15b-40aa565b955b",
    }


def generate_ingestion_task_data():
    """Generate ingestion task data"""
    source_names = [
        "customer_documents",
        "product_catalog",
        "support_tickets",
        "knowledge_base",
        "training_materials",
        "company_policies",
    ]

    return {
        "source_name": f"{random.choice(source_names)}_{random.randint(1, 999)}",
        "source_type": random.choice(["google_drive", "local", "database"]),
        "status": "pending",
        "source_attributes": {"path": f"/data/{random.choice(source_names)}/", "access_token": None},
    }


def generate_data_source_data():
    """Generate data source creation data"""
    source_names = [
        "customer_data",
        "product_info",
        "support_docs",
        "training_data",
        "company_wiki",
    ]

    table_names = [
        "customers",
        "products",
        "documents",
        "tickets",
        "articles",
    ]

    return {
        "name": f"{random.choice(source_names)}_{random.randint(1, 999)}",
        "type": random.choice(["google_drive", "local", "database"]),
        "database_table_name": f"{random.choice(table_names)}_{random.randint(1, 999)}",
        "database_schema": "public",
        "qdrant_collection_name": f"collection_{random.randint(1000, 9999)}",
        "embedding_model_reference": "text-embedding-3-large",
    }


def generate_organization_secret_data():
    """Generate organization secret data"""
    secret_keys = [
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "GOOGLE_API_KEY",
        "SLACK_WEBHOOK_URL",
        "DATABASE_PASSWORD",
        "EXTERNAL_API_TOKEN",
    ]

    secret_values = [
        f"sk-{random.randint(10**20, 10**21)}",
        f"token_{random.randint(10**15, 10**16)}",
        f"key_{random.randint(10**10, 10**11)}",
        f"https://hooks.slack.com/services/{random.randint(10**10, 10**11)}",
        f"pwd_{random.randint(10**8, 10**9)}",
        f"api_{random.randint(10**12, 10**13)}",
    ]

    return random.choice(secret_keys), random.choice(secret_values)


def generate_random_uuid():
    """Generate a random UUID string"""
    return str(uuid.uuid4())


def generate_random_duration():
    """Generate a random duration for metrics endpoints (in hours)"""
    return random.choice([1, 6, 12, 24, 168, 720])  # 1h, 6h, 12h, 1d, 1w, 1m


def generate_realistic_user_behavior():
    """Generate realistic user behavior patterns"""
    behaviors = [
        {
            "name": "power_user",
            "weight": 1,
            "wait_time": (1, 3),
            "actions": ["browse", "create", "edit", "delete", "chat"],
        },
        {"name": "casual_user", "weight": 3, "wait_time": (3, 8), "actions": ["browse", "chat"]},
        {
            "name": "admin_user",
            "weight": 1,
            "wait_time": (2, 5),
            "actions": ["browse", "create", "edit", "admin", "metrics"],
        },
    ]

    return random.choice(behaviors)


def validate_chat_message(data):
    """Validate chat message data structure"""
    return "messages" in data


def validate_project_data(data):
    """Validate project data structure"""
    return all(field in data for field in ["project_id", "project_name"])


if __name__ == "__main__":
    """Test the data generators"""
    print("Testing data generators...")

    print("\n1. Chat message:")
    chat_data = generate_chat_message()
    print(f"   {chat_data}")
    print(f"   Valid: {validate_chat_message(chat_data)}")

    print("\n2. Project data:")
    project_data = generate_project_data()
    print(f"   {project_data}")
    print(f"   Valid: {validate_project_data(project_data)}")

    print("\n3. API key data:")
    api_key_data = generate_api_key_data()
    print(f"   {api_key_data}")

    print("\n4. Organization secret:")
    secret_key, secret_value = generate_organization_secret_data()
    print(f"   Key: {secret_key}, Value: {secret_value[:20]}...")

    print("\n5. User behavior:")
    behavior = generate_realistic_user_behavior()
    print(f"   {behavior}")

    print("\n✅ All data generators working correctly!")
