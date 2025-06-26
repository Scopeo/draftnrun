# 🔥 FastAPI Load Testing with Locust

Complete load testing system for FastAPI backend with real-time monitoring using Grafana.

## 📋 What's included?

- **3 Testing Scenarios**: Basic, Authenticated, and Heavy Load
- **Real-time Monitoring**: Grafana dashboard integration
- **Realistic Data**: Data generators based on OpenAPI schemas
- **Automatic Authentication**: JWT tokens and API keys handling
- **Convenient Scripts**: Run tests with a single command

## 🏗️ Structure

```
scripts/load_testing/
├── locustfile.py              # Test scenarios definition
├── run_load_test.py           # Main script to run tests
├── README.md                  # This documentation
└── utils/
    ├── __init__.py
    ├── auth_helpers.py         # Authentication helpers
    └── data_generators.py      # Test data generators
```

## 🚀 Setup

### 1. Install load testing dependencies

```bash
uv sync --group load_testing
```

### 2. Verify FastAPI is running

```bash
curl http://localhost:8000/
```

### 3. Verify Grafana is working

```bash
curl http://localhost:3000/
```

## 📊 Testing Scenarios

### 🟢 Basic Scenario (No Auth)

**Perfect for initial demo**

- Endpoints: `/`, `/docs`, `/openapi.json`, `/metrics`
- No authentication required
- Ideal for showing metrics in Grafana

```bash
uv run python -m scripts.load_testing --scenario basic --users 10 --duration 60
```

### 🟡 Authenticated Scenario

**More realistic testing with API endpoints**

- Endpoints: projects, components, sources, metrics
- Requires valid JWT token
- Simulates real application usage

```bash
uv run python -m scripts.load_testing.run_load_test --scenario auth --users 5 --duration 120
```

### 🔴 Heavy Load Scenario

**Endpoints that could "kill" the backend**

- Endpoints: LLM chat, resource creation
- Use with caution
- Perfect for finding system limits

```bash
uv run python -m scripts.load_testing.run_load_test --scenario heavy --users 2 --duration 30
```

### 🔀 Mixed Load

**Combination of all scenarios**

```bash
uv run python -m scripts.load_testing.run_load_test --scenario all --users 15 --duration 180
```

## 🎯 Example Commands

### Quick Demo (60 seconds)

```bash
uv run python -m scripts.load_testing.run_load_test --scenario basic --users 10 --spawn-rate 2 --duration 60
```

### Stress Testing (5 minutes)

```bash
uv run python -m scripts.load_testing.run_load_test --scenario auth --users 20 --spawn-rate 1 --duration 300
```

### Interactive Mode (Web UI)

```bash
uv run python -m scripts.load_testing.run_load_test --scenario basic --interactive
# Then open http://localhost:8089
```

### Manual Testing with Locust

```bash
cd scripts/load_testing
uv run locust -f locustfile.py BasicEndpointsUser --host=http://localhost:8000
```

## 📈 Monitoring Results

### 1. **Grafana Dashboard** (Recommended)

- URL: http://localhost:3000
- Dashboard: "FastAPI Performance Dashboard"
- Real-time metrics: latency, throughput, errors

### 2. **Locust Web UI** (Interactive Mode)

- URL: http://localhost:8089
- Detailed statistics per endpoint
- Performance charts

### 3. **Terminal Output** (Headless Mode)

- Statistics summary at the end
- Real-time errors and warnings

## 🔧 Advanced Configuration

### Required Environment Variables

For authenticated scenarios, you need in your `credentials.env`:

```env
TEST_USER_EMAIL=your_email@example.com
TEST_USER_PASSWORD=your_password
INGESTION_API_KEY=your_api_key
```

### Customize Testing IDs

Edit `utils/auth_helpers.py` to change:

```python
def get_test_organization_id():
    return "your-org-id-here"

def get_test_project_id():
    return "your-project-id-here"
```

### Add New Endpoints

1. Edit `locustfile.py`
2. Add new `@task` methods
3. Use `utils/data_generators.py` for test data

## 🐛 Troubleshooting

### "Locust not found"

```bash
pip install locust
```

### "FastAPI server not accessible"

```bash
# Verify FastAPI is running
curl http://localhost:8000/

# Or start FastAPI
cd ada_backend
python main.py
```

### "Authentication setup failed"

- Check `credentials.env`
- Ensure `TEST_USER_EMAIL` and `TEST_USER_PASSWORD` are configured
- Verify the user exists in Supabase

### "No data in Grafana"

- Wait 30-60 seconds for metrics to appear
- Refresh the dashboard
- Check that Prometheus is scraping: http://localhost:9090/targets

### 422 errors on authenticated endpoints

- Normal for some test data
- Endpoints validate schemas strictly
- 422 errors are marked as "success" in testing

## 📚 Additional Resources

- [Locust Documentation](https://locust.io/)
- [Grafana Dashboards](http://localhost:3000)
- [Prometheus Metrics](http://localhost:9090)
- [FastAPI OpenAPI](http://localhost:8000/docs)
