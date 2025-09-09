# [Draft'n run](https://draftnrun.com)

We provide here a guide on how to set up **locally** your Draft'n run backend application.

## Set up the services

### Installations third-party packages

You will need to install the following packages:

- [Git](https://git-scm.com/book/en/v2/Getting-Started-Installing-Git)
- [Docker](https://docs.docker.com/engine/install/)
- [Docker Compose](https://docs.docker.com/compose/)
- [Supabase CLI](https://supabase.com/docs/guides/local-development/cli/getting-started?queryGroups=platform&platform=macos)

### Set up and run backend services

To use the backend of the app, you will need to run a Docker Compose file that launches the following services:

- postgres
- redis
- qdrant
- prometheus
- seaweedFS

#### Credentials for the services

You will need to create two env files related to those services:

- `.env` file in the `ada_ingestion_system` folder (you can copy the `.env.example` file)
- `credentials.env` at the root of the repository (you can copy the `credentials.env.example` file)

By default, the credentials to run those services on Docker Compose are the same as in the `credentials.env.example` and `.env.example` files, except
for the seaweedFS service.

For the seaweedFS service, you need to go to the config/seaweedfs folder and create a `s3_config.json` file
based on the same model as the `s3_config.json.example` file.
The credentials that you will put will give you access to the s3 service of seaweedFS.

Here are the env variables with the default values that work for Docker Compose:

- In `ada_ingestion_system/.env`:

  ```env
  # Redis configuration
  REDIS_HOST=localhost
  REDIS_PORT=6379
  REDIS_PASSWORD=redis_password
  REDIS_QUEUE_NAME=ada_ingestion_queue

  # Worker configuration
  MAX_CONCURRENT_INGESTIONS=2
  ```

- In `credentials.env`:

  ```env
  # For Ingestion, set INGESTION_DB_URL (required):
  INGESTION_DB_URL=postgresql://postgres:ada_password@localhost:5432/ada_ingestion

  # For Traces, set TRACES_DB_URL (required):
  TRACES_DB_URL=postgresql://postgres:ada_password@localhost:5432/ada_traces

  # FOR INGESTION QUEUE
  REDIS_HOST=localhost
  REDIS_PORT=6379
  REDIS_PASSWORD=redis_password
  REDIS_QUEUE_NAME=ada_ingestion_queue

  # DB for the backend
  ADA_DB_URL=postgresql://postgres:ada_password@localhost:5432/ada_backend

  # QDRANT
  QDRANT_CLUSTER_URL=http://localhost:6333
  QDRANT_API_KEY=secret_api_key

  # SeaweedFS
  # S3 CREDENTIALS FOR INGESTION
  S3_ENDPOINT_URL=http://localhost:8333
  S3_ACCESS_KEY_ID=your_s3_access_key_id
  S3_SECRET_ACCESS_KEY=your_s3_secret_access_key
  S3_BUCKET_NAME=s3-backend
  S3_REGION_NAME=us-east-1
  ```

  You will need to put in the `S3_ACCESS_KEY_ID` and the `S3_SECRET_ACCESS_KEY` the same values as in the `s3_config.json` file you created earlier.
  The `S3_BUCKET_NAME` is the name of the bucket created by the docker compose file, which is `s3-backend` by default.
  If you need to use seaweedfs on another machine, you can change the S3_ENDPOINT_URL accordingly.
  If you need to run the s3 service with amazon s3 or another s3-like service, you need to change those 5 variables.
  Be careful, when using amazon s3, put the `S3_ENDPOINT_URL` to None, meaning:

```env
S3_ENDPOINT_URL=
```

By default, boto3 will use the amazon s3 endpoint.

In general, if you want to modify the credentials for any of those services,
update the Docker Compose file accordingly.

### Service Configuration

Service configurations are in the `config/` folder. Some files are templates that get processed with environment variables from `credentials.env`. Templates use gomplate - install with `brew install gomplate` (macOS) or from https://github.com/hairyhenderson/gomplate/releases (Linux).

**Important**: Always run the render script before starting services to ensure consistency:

```bash
./scripts/render_configs.sh
```

This generates the `generated-config/` folder that Docker containers use.

To launch the services, navigate to the `services` folder and run:

```bash
docker compose up -d
```

To stop the services:

```bash
docker compose down -v
```

To clean the Docker volume if you suspect corruption:

```bash
docker volume prune
```

### Set up and run Supabase service

Supabase is the service needed to link the FrontEnd and Backend.

We provide a `supabase` folder with the configuration.

Once Supabase-Cli is installed, go to the root of the repository and run:

```bash
supabase start
```

This will create and launch Supabase.  
⚠️ **Warning:** The terminal will display secret values needed for the `.env` files of the Backend and FrontEnd. Store them.

To view them again later:

```bash
supabase status
```

##### Put Supabase values in credentials.env file

Here are two important variables that you get in the terminal when running supabase:

- **anon key**: `ey_...`
- **service_role key**: `eyJ...`

You need to use them to fill those environment variables:

```env
SUPABASE_PROJECT_KEY=*anon-key*
SUPABASE_SERVICE_ROLE_SECRET_KEY=*service_role key*
```

You will also need to run the edge runtime Supabase service in another terminal:

```bash
supabase functions serve
```

Expected output:

```bash
Setting up Edge Functions runtime...
Serving functions on http://127.0.0.1:54321/functions/v1/<function-name>
Using supabase-edge-runtime-1.67.4 (compatible with Deno v1.45.2)
```

Visit:

```bash
http://localhost:54323/
```

Then:

- Create a bucket in the **Storage** tab.
- Create a user in the **Authentication** tab.
- Use the **Table Editor** to add your user to one of the existing organizations.

#### Video tutorial

[Here](https://youtu.be/m9WCJ5mMD6w) is a quick video tutorial on how to set up those three things

#### Create a bucket in Supabase

Go to the **Storage** tab → **New Bucket**, and set a name.

⚠️ **Recommended:** Use `"ada-backend"` (default for `SUPABASE_BUCKET_NAME` in the backend).

To use a different name, add:

```env
SUPABASE_BUCKET_NAME=my_new_bucket
```

In your `credentials.env`.

#### Create a user account

Go to the **Authentication** tab and register a user (email/password).  
In **Table Editor**, check the `auth_user_emails` table for your user’s ID.

Store your username and password in credentials.env:

```env
SUPABASE_USERNAME=xxx
SUPABASE_PASSWORD=xxx
```

#### Add user to an organization

Use the **organization_members** table.

- `user_id` = your user’s ID from `auth_user_emails`
- `org_id` = the ID of the desired organization (e.g., `DraftNRun-test-organization` or `test2-organization`)
- `role` = your role in the organization (put admin to have all the rights)

#### Reset or stop Supabase

Reset database (clears data and buckets):

```bash
supabase db reset
```

Stop Supabase:

```bash
supabase stop
```

Clean Docker volume:

```bash
docker volume prune
```

At the end of this part, you should have filled those variables:

```env
SUPABASE_PROJECT_URL=http://localhost:54321
SUPABASE_PROJECT_KEY=*anon-key*
SUPABASE_SERVICE_ROLE_SECRET_KEY=*service_role key*

SUPABASE_USERNAME=xxx
SUPABASE_PASSWORD=xxx
SUPABASE_BUCKET_NAME=ada-backend
```

## Set up and run the backend

### Install Python packages

Use **UV**

1. [Install UV](https://docs.astral.sh/uv/getting-started/installation/#standalone-installer)
2. Create a virtual environment .venv:

```bash
uv venv
```

3. Activate it

```bash
source .venv/bin/activate
```

4. Install the packages

```bash
uv sync
```

### Credentials

Create the `credentials.env` file (copy from `credentials.env.example`).

Generate the secret keys for:

- `BACKEND_SECRET_KEY`

```bash
uv run python -c "import secrets; print(secrets.token_hex(32))"
```

- `FERNET_KEY`

```bash
uv run python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Fill Supabase values based on earlier [steps](#store-the-following-values):

```env
SUPABASE_PROJECT_URL=http://localhost:54321
SUPABASE_PROJECT_KEY=*anon-key*
SUPABASE_SERVICE_ROLE_SECRET_KEY=xxxx
SUPABASE_USERNAME=xxx@xxx.com
SUPABASE_PASSWORD=xxx
SUPABASE_BUCKET_NAME=ada-backend
```

Finally, generate with this script the INGESTION_API_KEY and the INGESTION_API_KEY_HASHED and put it in the credentials.env file:

```
uv run python -c "from ada_backend.services.api_key_service import _generate_api_key, _hash_key; key = _generate_api_key(); print('INGESTION_API_KEY =', key); print('INGESTION_API_KEY_HASHED =', _hash_key(key))"
```

```env
INGESTION_API_KEY=xxxx
INGESTION_API_KEY_HASHED=xxxx
```

#### Custom LLM Configuration

You can configure Draft'n run to use your own custom Large Language Model (LLM) service by adding the following variables to your `credentials.env` file:

You can configure Draft'n run to use your own custom Large Language Model (LLM) service by copying the `custom_models_example.json` one a `custom_models.json` file in the root directory.

**Configuration options:**

- **`completion_models`**: List of available completion models

  - `model_name`: The name of your model
  - `function_calling`: Whether the model supports function calling
  - `multimodal`: Whether the model supports multimodal inputs (images, etc.)
  - `constrained_completion_with_pydantic`: Whether the model supports Pydantic-constrained outputs
  - `constrained_completion_with_json_schema`: Whether the model supports JSON schema-constrained outputs

- **`embedding_models`**: List of available embedding models

  - `model_name`: The name of your embedding model
  - `embedding_size`: The dimension of the embeddings

- **`base_url`**: The API endpoint URL for your LLM provider
- **`api_key`**: Your API key for the provider

**Note:** If you dont have embedding models pass an empty list.

**3. Usage:**

Once configured, your custom models will appear in the model selection dropdowns throughout the application. You can reference them using the format `provider_name:model_name` (e.g., `your_provider_name:your-completion-model`).

**Note:** The `custom_models.json` file is automatically loaded by the application. No additional environment variables are required.

When you have done all configuration for local models you need to run seed again

```bash
make db-seed
```

**How it works:**  
If you set these variables, your custom model will appear as an option in the model selection dropdown after reseeding. When this model is selected, the backend will route requests to your custom LLM service instead of sending them to OpenAI or other providers.

#### Non-local version

Update these if using remote services:

```env
# QDRANT
QDRANT_CLUSTER_URL=xxxxx
QDRANT_API_KEY=xxxxx

# Supabase
SUPABASE_PROJECT_URL=http://localhost:54321
SUPABASE_PROJECT_KEY=xxxxx
SUPABASE_SERVICE_ROLE_SECRET_KEY=xxxx
SUPABASE_USERNAME=xxx@xxx.com
SUPABASE_PASSWORD=xxx
SUPABASE_BUCKET_NAME=ada-backend

# Redis
REDIS_HOST=xxxx
REDIS_PORT=6379
REDIS_PASSWORD=xxxx
REDIS_QUEUE_NAME=ada_ingestion_queue


# Ingestion
INGESTION_DB_URL=postgresql://postgres:ada_password@localhost:5432/ada_ingestion

# Backend DB
ADA_DB_URL=postgresql://postgres:ada_password@localhost:5432/ada_backend

# URL to run the backend app
ADA_URL=http://localhost:8000
```

#### Google OAuth Setup

To enable Google login, set these in your credentials.env:

```env
GOOGLE_CLIENT_ID=your-google-client-id
GOOGLE_CLIENT_SECRET=your-google-client-secret
```

How to get them:

- Go to Google Cloud Console.
- Create OAuth 2.0 credentials (type: Web application).
- Add your app’s redirect URI (e.g. https://yourdomain.com/auth/google/callback).
- Copy the Client ID and Client Secret and paste them above.

Make sure the redirect URI matches what you configure in Google and your app. Do not commit these secrets to version control.

### Set up the database for backend and ingestion

Ensure Postgres is running.

Then:

```bash
make db-upgrade
make db-seed
make trace-db-upgrade
```

Run the backend:

```bash
make run-draftnrun-agents-backend
```

#### How to visualize the docs of the backend endpoints/admin console

Define in the credentials.env your username password:

```env
ADMIN_USERNAME=your-admin-username
ADMIN_PASSWORD=your-admin-password
```

Relaunch the backend run and then go to the following url:

```
ADA_URL/docs (documentation swagger)
ADA_URL/admin (admin console)
```

If you run locally, `ADA_URL` in your credentials.env should be

```
ADA_URL=http://localhost:8000
```

#### Set up and run the ingestion worker

Ensure redis credentials are correctly set in both `.env` files.

Run the worker:

```bash
uv run python -m ada_ingestion_system.worker.main
```

## Backend Observability Stack

Draft'n run includes a comprehensive observability stack for monitoring, tracing, and performance analysis. The stack uses industry-standard open-source tools that provide production-ready monitoring capabilities.

### Observability Technologies

Our observability stack consists of:

- **🔥 Prometheus** - Metrics collection and storage for performance monitoring
- **📊 Grafana** - Visualization dashboards with real-time charts and alerts
- **🔍 Tempo** - Distributed tracing for request flow analysis
- **📈 FastAPI Metrics** - HTTP performance metrics (latency, throughput, errors)
- **🤖 Agent Metrics** - User-facing feature metrics for AI agent usage
- **🔄 Load Testing** - Locust-based performance testing with immediate dashboard feedback

This setup provides both **operational monitoring** (for DevOps) and **user-facing analytics** (for business insights).

### Environment Variables

The observability stack uses two types of variables:

**Backend connection variables** (what the backend uses to connect to observability services):

```env
# Backend connects to these endpoints
TEMPO_ENDPOINT=http://localhost:4318/v1/traces
PROMETHEUS_SERVER_URL=http://localhost:9090
GRAFANA_URL=http://localhost:3000
ENABLE_OBSERVABILITY_STACK=true
```

**Service configuration variables** (for service configuration):

```env
# Grafana datasource configuration
GRAFANA_PROMETHEUS_HOST=prometheus
GRAFANA_PROMETHEUS_PORT=9090
GRAFANA_TEMPO_HOST=tempo
GRAFANA_TEMPO_PORT=3200

# Grafana security
GF_SECURITY_ADMIN_USER=admin
GF_SECURITY_ADMIN_PASSWORD=admin

# Prometheus target configuration
PROMETHEUS_TARGET_BACKEND_HOST=host.docker.internal
PROMETHEUS_TARGET_BACKEND_HTTP_PORT=8000
PROMETHEUS_TARGET_BACKEND_AGENTS_PORT=9100
```

**For production**: Update the URLs in backend connection variables to point to your remote services.

### Enabling/Disabling Observability

You can enable or disable the observability stack with a single environment variable:

```env
ENABLE_OBSERVABILITY_STACK=true   # Default: enabled
ENABLE_OBSERVABILITY_STACK=false  # Disable instrumentation
```

When disabled, the backend runs normally without sending metrics or traces.

### Starting Observability Stack

Run the render script and launch the observability services:

```bash
./scripts/render_configs.sh
cd services
docker compose up -d prometheus grafana
```

Visit:

- Grafana: [http://localhost:3000](http://localhost:3000) (admin/admin if using default values)
- Prometheus: [http://localhost:9090](http://localhost:9090)

### Testing Your Setup

Use the provided scripts to validate metrics and tracing:

Health check:

```bash
./scripts/test_observability_stack.sh
```

Load testing:

```bash
uv run python -m scripts.load_testing --users 10 --duration 60
```

Then open Grafana and check the FastAPI Performance Dashboard or explore Prometheus targets to verify everything is flowing correctly.

For production, just update the environment variables and re-run the render script.

### Quick Start

1. **Generate configurations**:

```bash
./scripts/render_configs.sh
```

2. **Start services**:

```bash
cd services
docker compose up -d prometheus grafana
```

3. **Access dashboards**:
   - **Grafana**: http://localhost:3000 (admin/admin)
   - **Prometheus**: http://localhost:9090

**For production**: Update variables in `credentials.env` and regenerate configurations.

### Testing Your Setup

**Health check**:

```bash
./scripts/test_observability_stack.sh
```

This script will check if the components are correctly connected (FastAPI Backend, Prometheus, Tempo, Grafana)

**Load testing** (generates realistic metrics):

```bash
uv run python -m scripts.load_testing --users 10 --duration 60
```

**Dashboard access**: Login to Grafana and view "FastAPI Performance Dashboard".

## Developer Guide

### Logging convention

We use Python’s `logging` module with `logging-config.yaml` and `logger.py`.

#### Setup logging

At the app entry point:

```python
from logger import setup_logging

setup_logging()
```

#### Use logger

```python
import logging

LOGGER = logging.getLogger(__name__)

def some_function():
    LOGGER.info("Info message from some_function")
```

### Tracing

For more details, see the [tracing documentation](engine/trace/README.md).

## AI Models

AI models are the primary agents that you can run

- **AI Agent**: Agent that handle conversation with tools access capacity
- **RAG** : Agent that retrieves information from documents to answer
- **LLM Call**: Templated LLM Call
- **Database Query Agent**: Agent able to interrogate a SQL database

## Input

The input block is at the begining of each flow. It allows the user to determine what information the AI agent can use during the flow.

## Tools

Tools are available for the AI Agent. Note that the AI Agent can also have other AI models as tools

### Tool description

- **API call**: A generic API tool that can make HTTP requests to any API endpoint.
- **Internet Search with OpenAI**: Answer a question using web search.
- **SQL tool**: Builds SQL queries from natural language
- **RunSQLquery tool**: Builds and executes SQL queries
