# Future: K8s Migration Plan (Phase 2+)

This document outlines the plan for migrating from EC2/systemd to Kubernetes with ARM support.

**Prerequisites:** Complete Phase 1 (graceful shutdown) first.

---

## Phase 2: Containerization

### Dockerfiles

**Dockerfile.api**
```dockerfile
FROM python:3.11-slim as builder
WORKDIR /app
RUN apt-get update && apt-get install -y build-essential libpq-dev && rm -rf /var/lib/apt/lists/*
RUN pip install uv
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

FROM python:3.11-slim
WORKDIR /app
RUN apt-get update && apt-get install -y libpq5 curl && rm -rf /var/lib/apt/lists/*
COPY --from=builder /app/.venv /app/.venv
COPY ada_backend/ ./ada_backend/
COPY engine/ ./engine/
COPY data_ingestion/ ./data_ingestion/
COPY settings.py logger.py ./
ENV PATH="/app/.venv/bin:$PATH" PYTHONPATH="/app"
HEALTHCHECK --interval=30s --timeout=10s CMD curl -f http://localhost:8000/health || exit 1
EXPOSE 8000
CMD ["gunicorn", "-w", "2", "-k", "uvicorn.workers.UvicornWorker", "ada_backend.main:app", "--bind", "0.0.0.0:8000", "--timeout", "1800", "--graceful-timeout", "1800"]
```

**Dockerfile.worker**
```dockerfile
FROM python:3.11-slim as builder
WORKDIR /app
RUN apt-get update && apt-get install -y build-essential libpq-dev && rm -rf /var/lib/apt/lists/*
RUN pip install uv
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

FROM python:3.11-slim
WORKDIR /app
RUN apt-get update && apt-get install -y libpq5 && rm -rf /var/lib/apt/lists/*
COPY --from=builder /app/.venv /app/.venv
COPY ada_ingestion_system/ ./ada_ingestion_system/
COPY ada_backend/ ./ada_backend/
COPY engine/ ./engine/
COPY data_ingestion/ ./data_ingestion/
COPY settings.py logger.py ./
ENV PATH="/app/.venv/bin:$PATH" PYTHONPATH="/app"
CMD ["python", "-m", "ada_ingestion_system.worker.main"]
```

**Dockerfile.scheduler**
```dockerfile
FROM python:3.11-slim as builder
WORKDIR /app
RUN apt-get update && apt-get install -y build-essential libpq-dev && rm -rf /var/lib/apt/lists/*
RUN pip install uv
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

FROM python:3.11-slim
WORKDIR /app
RUN apt-get update && apt-get install -y libpq5 && rm -rf /var/lib/apt/lists/*
COPY --from=builder /app/.venv /app/.venv
COPY ada_backend/ ./ada_backend/
COPY engine/ ./engine/
COPY settings.py logger.py ./
ENV PATH="/app/.venv/bin:$PATH" PYTHONPATH="/app"
CMD ["python", "-m", "ada_backend.run_scheduler"]
```

### Multi-Arch Build Workflow

**.github/workflows/build-images.yml**
```yaml
name: Build Multi-Arch Docker Images

on:
  push:
    branches: [main, staging]

env:
  REGISTRY: ghcr.io
  IMAGE_PREFIX: ${{ github.repository }}

jobs:
  build:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        service: [api, worker, scheduler]
    steps:
      - uses: actions/checkout@v4
      - uses: docker/setup-qemu-action@v3
      - uses: docker/setup-buildx-action@v3

      - name: Login to Registry
        uses: docker/login-action@v3
        with:
          registry: ${{ env.REGISTRY }}
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}

      - name: Build and push
        uses: docker/build-push-action@v5
        with:
          context: .
          file: Dockerfile.${{ matrix.service }}
          platforms: linux/amd64,linux/arm64
          push: true
          tags: |
            ${{ env.REGISTRY }}/${{ env.IMAGE_PREFIX }}-${{ matrix.service }}:${{ github.sha }}
            ${{ env.REGISTRY }}/${{ env.IMAGE_PREFIX }}-${{ matrix.service }}:latest
          cache-from: type=gha
          cache-to: type=gha,mode=max
```

---

## Phase 3: ARM EC2 Setup with k3s

### Instance Specs
- **Instance Type**: `m7g.xlarge` (4 vCPU, 16GB) or `m7g.2xlarge`
- **AMI**: Amazon Linux 2023 ARM64
- **Storage**: 100GB gp3 SSD

### Setup Script
```bash
#!/bin/bash
# Run as root

# Update system
dnf update -y

# Install Docker
dnf install -y docker
systemctl enable --now docker
usermod -aG docker ec2-user

# Install k3s (lightweight K8s)
curl -sfL https://get.k3s.io | sh -s - --write-kubeconfig-mode 644

# Install Helm
curl https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash

# Configure kubectl for ec2-user
mkdir -p /home/ec2-user/.kube
cp /etc/rancher/k3s/k3s.yaml /home/ec2-user/.kube/config
chown -R ec2-user:ec2-user /home/ec2-user/.kube
```

---

## Phase 4: Kubernetes Manifests

### API Deployment (Rolling Updates)

**infra/k8s/api-deployment.yaml**
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: ada-api
spec:
  replicas: 2
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1
      maxUnavailable: 0
  selector:
    matchLabels:
      app: ada-api
  template:
    metadata:
      labels:
        app: ada-api
    spec:
      terminationGracePeriodSeconds: 1800
      containers:
      - name: ada-api
        image: ghcr.io/your-org/ada-api:latest
        ports:
        - containerPort: 8000
        resources:
          requests:
            cpu: "500m"
            memory: "1Gi"
          limits:
            cpu: "2000m"
            memory: "4Gi"
        readinessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 10
          periodSeconds: 5
        livenessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 30
          periodSeconds: 10
        envFrom:
        - secretRef:
            name: ada-secrets
        lifecycle:
          preStop:
            exec:
              command: ["/bin/sh", "-c", "sleep 5"]
---
apiVersion: v1
kind: Service
metadata:
  name: ada-api
spec:
  type: LoadBalancer
  ports:
  - port: 80
    targetPort: 8000
  selector:
    app: ada-api
```

### Worker Deployment

**infra/k8s/worker-deployment.yaml**
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: ada-worker
spec:
  replicas: 1
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1
      maxUnavailable: 0
  selector:
    matchLabels:
      app: ada-worker
  template:
    metadata:
      labels:
        app: ada-worker
    spec:
      terminationGracePeriodSeconds: 1800
      containers:
      - name: ada-worker
        image: ghcr.io/your-org/ada-worker:latest
        resources:
          requests:
            cpu: "1000m"
            memory: "2Gi"
          limits:
            cpu: "4000m"
            memory: "8Gi"
        envFrom:
        - secretRef:
            name: ada-secrets
```

### Scheduler Deployment

**infra/k8s/scheduler-deployment.yaml**
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: ada-scheduler
spec:
  replicas: 1
  strategy:
    type: Recreate  # Only 1 scheduler at a time
  selector:
    matchLabels:
      app: ada-scheduler
  template:
    metadata:
      labels:
        app: ada-scheduler
    spec:
      terminationGracePeriodSeconds: 1800
      containers:
      - name: ada-scheduler
        image: ghcr.io/your-org/ada-scheduler:latest
        resources:
          requests:
            cpu: "250m"
            memory: "512Mi"
        envFrom:
        - secretRef:
            name: ada-secrets
```

### DB Migration Job

**infra/k8s/migration-job.yaml**
```yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: ada-migration-{{ .Values.version }}
spec:
  template:
    spec:
      restartPolicy: Never
      containers:
      - name: migration
        image: ghcr.io/your-org/ada-api:latest
        command: ["sh", "-c", "alembic upgrade head && python -m ada_backend.scripts.seed_db"]
        envFrom:
        - secretRef:
            name: ada-secrets
  backoffLimit: 3
```

---

## Phase 5: GitHub Actions CD

**.github/workflows/deploy-k8s-prod.yml**
```yaml
name: Deploy to Production (K8s)

on:
  push:
    branches: [main]

jobs:
  migrate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Configure kubectl
        uses: azure/k8s-set-context@v3
        with:
          kubeconfig: ${{ secrets.KUBECONFIG }}

      - name: Run migrations
        run: |
          kubectl apply -f infra/k8s/migration-job.yaml
          kubectl wait --for=condition=complete job/ada-migration --timeout=300s

  deploy:
    needs: migrate
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Configure kubectl
        uses: azure/k8s-set-context@v3
        with:
          kubeconfig: ${{ secrets.KUBECONFIG }}

      - name: Update deployments
        run: |
          kubectl set image deployment/ada-api ada-api=ghcr.io/your-org/ada-api:${{ github.sha }}
          kubectl set image deployment/ada-worker ada-worker=ghcr.io/your-org/ada-worker:${{ github.sha }}
          kubectl set image deployment/ada-scheduler ada-scheduler=ghcr.io/your-org/ada-scheduler:${{ github.sha }}

      - name: Wait for rollout
        run: |
          kubectl rollout status deployment/ada-api --timeout=35m
          kubectl rollout status deployment/ada-worker --timeout=35m
          kubectl rollout status deployment/ada-scheduler --timeout=35m
```

---

## How K8s Rolling Update Works

```
Time 0:  [Pod-v1] [Pod-v1]           <- 2 old pods running

Push to main → triggers deployment

Time 1:  [Pod-v1] [Pod-v1] [Pod-v2]  <- New pod starting (maxSurge=1)
                           ↑ starting

Time 2:  [Pod-v1] [Pod-v1] [Pod-v2]  <- New pod passes readiness probe
                           ✓ ready

Time 3:  [Pod-v1] [Pod-v2] [Pod-v2]  <- Old pod receives SIGTERM
         ↑ draining (30 min grace)

Time 4:  [Pod-v2] [Pod-v2]           <- All pods updated
```

Key settings:
- `maxSurge: 1` - Run 1 extra pod during rollout
- `maxUnavailable: 0` - Never kill old pod until new is ready
- `terminationGracePeriodSeconds: 1800` - 30 min to finish work after SIGTERM

---

## Migration Checklist

1. [ ] Phase 1 complete (graceful shutdown working on EC2)
2. [ ] Create ECR repositories (ada-api, ada-worker, ada-scheduler)
3. [ ] Test Docker builds locally
4. [ ] Set up ARM EC2 instance with k3s
5. [ ] Create K8s secrets from env vars
6. [ ] Deploy to K8s (staging first)
7. [ ] Test rolling updates with long-running tasks
8. [ ] Switch DNS/LB to K8s
9. [ ] Monitor for 1 week
10. [ ] Decommission old EC2 instances
