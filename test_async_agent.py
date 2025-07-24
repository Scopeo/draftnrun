import asyncio
import aiohttp
import requests
import time
import argparse
import sys
from typing import List, Dict, Any
import json

# Default Configuration
DEFAULT_API_KEY = "taylor_7DB4viOiRaacFjiZohd0FH0xlTtEqOtX"
DEFAULT_PROJECT_ID = "05453331-f021-48c6-9e66-a9bd997402e8"
DEFAULT_BASE_URL = "http://localhost:8000"


def parse_arguments():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Test async agent functionality with configurable project and API key",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python test_async_agent.py
  python test_async_agent.py --project-id "your-project-id" --api-key "your-api-key"
  python test_async_agent.py -p "your-project-id" -k "your-api-key" --base-url "https://your-server.com"
  python test_async_agent.py --single-test
        """,
    )

    parser.add_argument(
        "--project-id",
        "-p",
        type=str,
        default=DEFAULT_PROJECT_ID,
        help=f"Project ID to test (default: {DEFAULT_PROJECT_ID})",
    )

    parser.add_argument(
        "--api-key",
        "-k",
        type=str,
        default=DEFAULT_API_KEY,
        help=f"API key for authentication (default: {DEFAULT_API_KEY})",
    )

    parser.add_argument(
        "--base-url",
        "-u",
        type=str,
        default=DEFAULT_BASE_URL,
        help=f"Base URL for the API (default: {DEFAULT_BASE_URL})",
    )

    parser.add_argument("--single-test", action="store_true", help="Run only the single request test")

    parser.add_argument(
        "--concurrent-requests", "-c", type=int, default=3, help="Number of concurrent requests to test (default: 3)"
    )

    parser.add_argument(
        "--stress-requests", "-s", type=int, default=5, help="Number of stress test requests (default: 5)"
    )

    parser.add_argument("--verbose", "-v", action="store_true", help="Enable verbose output")

    return parser.parse_args()


def setup_configuration(args):
    """Setup configuration based on command line arguments."""
    global API_KEY, PROJECT_ID, BASE_URL, URL, headers

    API_KEY = args.api_key
    PROJECT_ID = args.project_id
    BASE_URL = args.base_url
    URL = f"{BASE_URL}/projects/{PROJECT_ID}/production/run"

    headers = {"X-API-Key": API_KEY, "Content-Type": "application/json"}

    if args.verbose:
        print(f"🔧 Configuration:")
        print(f"   Project ID: {PROJECT_ID}")
        print(f"   Base URL: {BASE_URL}")
        print(f"   API Key: {API_KEY[:10]}...{API_KEY[-4:] if len(API_KEY) > 14 else '***'}")
        print(f"   Full URL: {URL}")
        print()


# Configuration (will be set by setup_configuration)
API_KEY = DEFAULT_API_KEY
PROJECT_ID = DEFAULT_PROJECT_ID
BASE_URL = DEFAULT_BASE_URL
URL = f"{BASE_URL}/projects/{PROJECT_ID}/production/run"

headers = {"X-API-Key": API_KEY, "Content-Type": "application/json"}


async def test_async_agent_single_request():
    """Test a single async request to the agent."""
    payload = {"messages": [{"role": "user", "content": "Hello, how are you?"}]}

    async with aiohttp.ClientSession() as session:
        async with session.post(URL, json=payload, headers=headers) as response:
            if response.status == 200:
                result = await response.json()
                print("✅ Async single request successful:", result)
                return result
            else:
                error_text = await response.text()
                print(f"❌ Async single request failed: {response.status} - {error_text}")
                return None


async def test_async_agent_concurrent_requests(num_requests: int = 5):
    """Test multiple concurrent async requests to the agent."""
    payloads = [
        {"messages": [{"role": "user", "content": f"Request {i}: What is the capital of France?"}]}
        for i in range(num_requests)
    ]

    async def make_request(payload: Dict[str, Any], request_id: int):
        start_time = time.time()
        async with aiohttp.ClientSession() as session:
            async with session.post(URL, json=payload, headers=headers) as response:
                end_time = time.time()
                duration = end_time - start_time

                if response.status == 200:
                    result = await response.json()
                    print(f"✅ Request {request_id} completed in {duration:.2f}s")
                    return {"success": True, "duration": duration, "result": result}
                else:
                    error_text = await response.text()
                    print(f"❌ Request {request_id} failed in {duration:.2f}s: {response.status} - {error_text}")
                    return {"success": False, "duration": duration, "error": error_text}

    print(f"\n🚀 Starting {num_requests} concurrent async requests...")
    start_time = time.time()

    # Create tasks for concurrent execution
    tasks = [make_request(payload, i) for i, payload in enumerate(payloads)]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    end_time = time.time()
    total_duration = end_time - start_time

    # Analyze results
    successful_requests = sum(1 for r in results if isinstance(r, dict) and r.get("success"))
    failed_requests = len(results) - successful_requests

    print(f"\n📊 Concurrent Request Results:")
    print(f"   Total requests: {num_requests}")
    print(f"   Successful: {successful_requests}")
    print(f"   Failed: {failed_requests}")
    print(f"   Total time: {total_duration:.2f}s")
    print(f"   Average time per request: {total_duration/num_requests:.2f}s")

    return results


async def test_async_agent_complex_queries():
    """Test the agent with more complex queries that might trigger async operations."""
    complex_queries = [
        "Can you search the web for the latest news about artificial intelligence?",
        "Search for restaurants near Sannois France for burgers and provide the rating.",
        "Please analyze this document and provide a summary: The future of AI in healthcare.",
        "What are the current trends in machine learning? Please provide recent examples.",
        "Can you help me understand quantum computing and its applications?",
        "Please find information about renewable energy technologies and their efficiency.",
        "Search for information about the size of France most populated cities and print a graph of the results with an histogram form",
    ]

    async def test_complex_query(query: str, query_id: int):
        payload = {"messages": [{"role": "user", "content": query}]}

        start_time = time.time()
        async with aiohttp.ClientSession() as session:
            async with session.post(URL, json=payload, headers=headers) as response:
                end_time = time.time()
                duration = end_time - start_time

                if response.status == 200:
                    result = await response.json()
                    print(f"✅ Complex query {query_id} completed in {duration:.2f}s")
                    return {"success": True, "duration": duration, "query": query, "result": result}
                else:
                    error_text = await response.text()
                    print(f"❌ Complex query {query_id} failed in {duration:.2f}s: {response.status} - {error_text}")
                    print(f"   Query: {query[:100]}{'...' if len(query) > 100 else ''}")
                    return {"success": False, "duration": duration, "query": query, "error": error_text}

    print(f"\n🧠 Testing complex queries that might trigger async operations...")
    start_time = time.time()

    tasks = [test_complex_query(query, i) for i, query in enumerate(complex_queries)]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    end_time = time.time()
    total_duration = end_time - start_time

    successful_queries = sum(1 for r in results if isinstance(r, dict) and r.get("success"))
    failed_queries = len(results) - successful_queries

    print(f"\n📊 Complex Query Results:")
    print(f"   Total queries: {len(complex_queries)}")
    print(f"   Successful: {successful_queries}")
    print(f"   Failed: {failed_queries}")
    print(f"   Total time: {total_duration:.2f}s")
    print(f"   Average time per query: {total_duration/len(complex_queries):.2f}s")

    # Print failed queries summary
    if failed_queries > 0:
        print(f"\n❌ Failed Queries Summary:")
        for i, result in enumerate(results):
            if isinstance(result, dict) and not result.get("success"):
                print(f"   Query {i}: {result['query'][:80]}{'...' if len(result['query']) > 80 else ''}")

    return results


async def test_sync_vs_async_comparison():
    """Compare sync vs async performance for the same requests."""
    payload = {"messages": [{"role": "user", "content": "Hello, how are you?"}]}

    print("\n🔄 Comparing sync vs async performance...")

    # Test sync request
    start_time = time.time()
    sync_response = requests.post(URL, json=payload, headers=headers)
    sync_duration = time.time() - start_time

    if sync_response.status_code == 200:
        print(f"✅ Sync request completed in {sync_duration:.2f}s")
    else:
        print(f"❌ Sync request failed: {sync_response.status_code} - {sync_response.text}")

    # Test async request
    start_time = time.time()
    async with aiohttp.ClientSession() as session:
        async with session.post(URL, json=payload, headers=headers) as response:
            end_time = time.time()
            async_duration = end_time - start_time

            if response.status == 200:
                print(f"✅ Async request completed in {async_duration:.2f}s")
            else:
                error_text = await response.text()
                print(f"❌ Async request failed: {response.status} - {error_text}")
                return

    if async_duration:
        improvement = ((sync_duration - async_duration) / sync_duration) * 100
        print(f"📈 Performance comparison:")
        print(f"   Sync: {sync_duration:.2f}s")
        print(f"   Async: {async_duration:.2f}s")
        print(f"   Improvement: {improvement:.1f}%")


async def test_async_agent_stress_test(num_requests: int = 10, delay: float = 0.1):
    """Stress test the async agent with controlled concurrency."""
    print(f"\n🔥 Stress testing with {num_requests} requests and {delay}s delay...")

    async def stress_request(request_id: int):
        payload = {"messages": [{"role": "user", "content": f"Stress test request {request_id}: Tell me a joke"}]}

        start_time = time.time()
        async with aiohttp.ClientSession() as session:
            async with session.post(URL, json=payload, headers=headers) as response:
                end_time = time.time()
                duration = end_time - start_time

                if response.status == 200:
                    result = await response.json()
                    print(f"✅ Stress request {request_id} completed in {duration:.2f}s")
                    return {"success": True, "duration": duration, "request_id": request_id}
                else:
                    error_text = await response.text()
                    print(f"❌ Stress request {request_id} failed in {duration:.2f}s: {response.status}")
                    return {"success": False, "duration": duration, "request_id": request_id, "error": error_text}

    # Create tasks with controlled concurrency
    tasks = []
    for i in range(num_requests):
        task = asyncio.create_task(stress_request(i))
        tasks.append(task)
        await asyncio.sleep(delay)  # Add delay between task creation

    start_time = time.time()
    results = await asyncio.gather(*tasks, return_exceptions=True)
    total_duration = time.time() - start_time

    successful_requests = sum(1 for r in results if isinstance(r, dict) and r.get("success"))
    failed_requests = len(results) - successful_requests

    print(f"\n📊 Stress Test Results:")
    print(f"   Total requests: {num_requests}")
    print(f"   Successful: {successful_requests}")
    print(f"   Failed: {failed_requests}")
    print(f"   Total time: {total_duration:.2f}s")
    print(f"   Requests per second: {num_requests/total_duration:.2f}")

    return results


async def test_async_agent_error_handling():
    """Test how the agent handles various error conditions."""
    print("\n🔍 Testing error handling...")

    test_cases = [
        {"name": "Empty message", "payload": {"messages": []}},
        {"name": "Invalid message format", "payload": {"messages": [{"invalid": "format"}]}},
        {"name": "Very long message", "payload": {"messages": [{"role": "user", "content": "A" * 10000}]}},
        {
            "name": "Special characters",
            "payload": {
                "messages": [{"role": "user", "content": "Test with émojis 🚀 and special chars: !@#$%^&*()"}]
            },
        },
    ]

    async def test_error_case(test_case: Dict[str, Any]):
        async with aiohttp.ClientSession() as session:
            async with session.post(URL, json=test_case["payload"], headers=headers) as response:
                if response.status == 200:
                    result = await response.json()
                    print(f"✅ {test_case['name']}: Unexpected success")
                    return {"success": True, "name": test_case["name"]}
                else:
                    error_text = await response.text()
                    print(f"❌ {test_case['name']}: {response.status} - {error_text[:100]}...")
                    return {"success": False, "name": test_case["name"], "status": response.status}

    tasks = [test_error_case(test_case) for test_case in test_cases]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    print(f"\n📊 Error Handling Results:")
    for result in results:
        if isinstance(result, dict):
            status = "✅ Success" if result.get("success") else f"❌ Failed ({result.get('status', 'Unknown')})"
            print(f"   {result['name']}: {status}")


async def run_all_async_tests(args):
    """Run all async tests in sequence."""
    print("🚀 Starting comprehensive async agent tests...")
    print("=" * 60)

    # Test 1: Single async request
    print("\n1️⃣ Testing single async request...")
    await test_async_agent_single_request()

    if args.single_test:
        print("\n" + "=" * 60)
        print("✅ Single test completed!")
        return

    # Test 2: Concurrent requests
    print("\n2️⃣ Testing concurrent requests...")
    await test_async_agent_concurrent_requests(args.concurrent_requests)

    # Test 3: Complex queries
    print("\n3️⃣ Testing complex queries...")
    await test_async_agent_complex_queries()

    # Test 4: Sync vs Async comparison
    print("\n4️⃣ Comparing sync vs async performance...")
    await test_sync_vs_async_comparison()

    # Test 5: Error handling
    print("\n5️⃣ Testing error handling...")
    await test_async_agent_error_handling()

    # Test 6: Stress test
    print("\n6️⃣ Running stress test...")
    await test_async_agent_stress_test(args.stress_requests, 0.5)

    print("\n" + "=" * 60)
    print("✅ All async tests completed!")


async def main():
    """Main function to run the tests."""
    try:
        args = parse_arguments()
        setup_configuration(args)
        await run_all_async_tests(args)
    except KeyboardInterrupt:
        print("\n\n⏹️  Tests interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ Error running tests: {e}")
        sys.exit(1)


if __name__ == "__main__":
    # Run all tests
    asyncio.run(main())
