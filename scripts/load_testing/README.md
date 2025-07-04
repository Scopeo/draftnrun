# FastAPI Load Testing

Simple load testing setup for FastAPI applications using Locust. Perfect for demonstrating system performance and monitoring with Grafana dashboards.

## 🚀 Quick Start

### Prerequisites

1. **Install dependencies:**

   ```bash
   uv sync --group load_testing
   ```

2. **Start your FastAPI server:**

   ```bash
   # Make sure your FastAPI app is running on http://localhost:8000
   cd ada_backend
   python main.py
   ```

3. **Run a basic load test:**
   ```bash
   uv run python -m scripts.load_testing --users 10 --duration 30
   ```

## 📊 Usage Examples

### Basic Demo (Recommended for first-time use)

```bash
# 10 users, 2/sec spawn rate, 60 seconds
uv run python -m scripts.load_testing --users 10 --spawn-rate 2 --duration 60
```

### High Load Testing

```bash
# 25 users, 5/sec spawn rate, 30 seconds
uv run python -m scripts.load_testing --users 25 --spawn-rate 5 --duration 30
```

### Interactive Mode (Web UI)

```bash
# Opens Locust web interface at http://localhost:8089
uv run python -m scripts.load_testing --users 10 --interactive
```

### Custom Host

```bash
# Test against different host
uv run python -m scripts.load_testing --host http://staging.example.com --users 5
```

## 🎯 What Gets Tested

The load tests target these FastAPI endpoints:

- **`GET /`** - Welcome message (50% of requests)
- **`GET /docs`** - Swagger documentation (30% of requests)
- **`GET /openapi.json`** - OpenAPI specification (20% of requests)
- **`GET /metrics`** - Prometheus metrics (10% of requests)

## 📈 Monitoring Results

### Grafana Dashboard (Recommended)

- URL: http://localhost:3000
- Real-time metrics: latency, throughput, errors
- Best way to visualize load test impact

### Locust Web UI (Interactive Mode)

- URL: http://localhost:8089 (when using `--interactive`)
- Detailed statistics per endpoint
- Performance charts and real-time monitoring

### Terminal Output (Headless Mode)

- Statistics summary at the end
- Real-time errors and warnings
- Quick performance overview

## 🔧 Command Line Options

```bash
uv run python -m scripts.load_testing [OPTIONS]

Options:
  --users INTEGER          Number of concurrent users (default: 10)
  --spawn-rate INTEGER     User spawn rate per second (default: 2)
  --duration INTEGER       Test duration in seconds (default: 60)
  --host TEXT             Target host URL (default: http://localhost:8000)
  --interactive           Run in interactive mode (opens web UI)
  --skip-validation       Skip prerequisite validation
  --help                  Show this message and exit
```

## 🐛 Troubleshooting

### "Locust not found"

```bash
uv sync --group load_testing
```

### "FastAPI server not accessible"

```bash
# Verify FastAPI is running
curl http://localhost:8000/

# Or start FastAPI
cd ada_backend
python main.py
```

### "No data in Grafana"

- Wait 30-60 seconds for metrics to appear
- Refresh the dashboard
- Check that Prometheus is scraping: http://localhost:9090/targets

## 📚 Manual Testing with Locust

For advanced users who want to run Locust directly:

```bash
cd scripts/load_testing
locust -f locustfile.py BasicEndpointsUser --host=http://localhost:8000
```

## 🎉 Integration with Observability Stack

This load testing system is designed to work seamlessly with the existing observability infrastructure:

- **OpenTelemetry** → Captures request traces and metrics
- **Prometheus** → Scrapes and stores performance metrics
- **Tempo** → Distributed tracing storage
- **Grafana** → Real-time dashboard visualization

Run load tests and immediately see the impact on your Grafana dashboards!

## 📚 Resources

- [Locust Documentation](https://locust.io/)
- [Grafana Dashboards](http://localhost:3000)
- [Prometheus Metrics](http://localhost:9090)
- [FastAPI OpenAPI](http://localhost:8000/docs)
