# DraftNRun

We provide here a guide on how to set up **locally** your DraftNRun backend application.

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

#### Credentials for the services

You will need to create two env files related to those services:

- `.env` file in the `ada_ingestion_system` folder (you can copy the `.env.example` file)
- `credentials.env` at the root of the repository (you can copy the `credentials.env.example` file)

By default, the credentials to run those services on Docker Compose are the same as in the `credentials.env.example` and `.env` files.

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
  ```

If you want to modify these credentials, update the Docker Compose file accordingly.

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

##### Store the following values

- **anon key**: `ey_...`
- **service_role key**: `eyJ...`

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
#python -c "from ada_backend.services.api_key_service import _generate_api_key, _hash_key; key = _generate_api_key(); print('INGESTION_API_KEY =', key); print('INGESTION_API_KEY_HASHED =', _hash_key(key))"

```env
INGESTION_API_KEY=xxxx
INGESTION_API_KEY_HASHED=xxxx
```

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

#### Set up and run the ingestion worker

Ensure redis credentials are correctly set in both `.env` files.

Run the worker:

```bash
uv run python -m ada_ingestion_system.worker.main
```

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

