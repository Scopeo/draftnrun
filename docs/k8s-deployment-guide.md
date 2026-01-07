# K8s Deployment Guide

## Overview

This guide covers the Kubernetes deployment system using k3s on EC2 with GitHub Actions CI/CD.

```
                     ghcr.io (PUBLIC)
    ┌─────────────────────────────────────────────┐
    │  scopeo/draftnrun-api:latest                │
    │  scopeo/draftnrun-worker:latest             │
    │  scopeo/draftnrun-scheduler:latest          │
    └─────────────────────────────────────────────┘
              │              │              │
              ▼              ▼              ▼
       ┌──────────┐   ┌──────────┐   ┌──────────┐
       │ Staging  │   │   Prod   │   │ Customer │
       │   K8s    │   │   K8s    │   │ On-Prem  │
       │ (EC2 #1) │   │ (EC2 #2) │   │ (docker) │
       └──────────┘   └──────────┘   └──────────┘
```

---

## 1. GitHub Secrets Setup

### Required Secrets

Go to: **GitHub Repo → Settings → Secrets and variables → Actions → New repository secret**

| Secret | Value |
|--------|-------|
| `EC2_HOST_K8S_STAGING` | `<staging-ec2-ip>` |
| `EC2_HOST_K8S_PROD` | `<prod-ec2-ip>` |
| `SSH_PRIVATE_KEY` | `<your-ssh-key>` |

---

## 2. Launch New EC2 for Prod

### 2.1 Create EC2 Instance (AWS Console)

**Template arm k3s:**

use the template and change your ssh keys

☕️ wait a few minutes for the script to finish running

ssh into the instance and check if done with `cloud-init status`

### 2.3 Create Namespace

```bash
kubectl create namespace ada-prod
```

### 2.4 Initial Deployment

```bash
# Create secrets (see Section 3)
kubectl create secret generic ada-secrets -n ada-prod \
  --from-env-file=credentials.env

# Apply manifests (if using Kustomize)
kubectl apply -k k8s/overlays/prod

# Or apply directly
kubectl apply -f k8s/base/ -n ada-prod
```

---

## 3. Credentials/Config Setup

### 3.1 Create credentials.env

On the EC2, create a file with your secrets:

```bash
cat > credentials.env << 'EOF'
# Database
POSTGRES_HOST=your-db-host.rds.amazonaws.com
POSTGRES_PORT=5432
POSTGRES_DB=ada
POSTGRES_USER=ada_user
POSTGRES_PASSWORD=your-secure-password

# Redis
REDIS_URL=redis://localhost:6379

# AI Providers
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...

# Add other secrets as needed
EOF
```

### 3.2 Apply to Kubernetes

```bash
# Create secret from env file
kubectl create secret generic ada-secrets -n ada-prod \
  --from-env-file=credentials.env

# Or update existing secret
kubectl delete secret ada-secrets -n ada-prod
kubectl create secret generic ada-secrets -n ada-prod \
  --from-env-file=credentials.env

# Restart pods to pick up new secrets
kubectl rollout restart deployment -n ada-prod
```

### 3.3 Verify Secrets

```bash
# List secrets
kubectl get secrets -n ada-prod

# View secret keys (not values)
kubectl describe secret ada-secrets -n ada-prod
```

---

## 4. Deploy System Overview

### Workflows

| Workflow | Trigger | What it does |
|----------|---------|--------------|
| `build-and-deploy-k8s.yml` | Manual dispatch | Build images → Push to ghcr.io → Deploy to K8s |
| `reset-k8s-staging-to-main.yml` | Manual dispatch | Downgrade migrations → Deploy `:main` image → Upgrade |

### Image Tagging

| Event | Tags Applied |
|-------|--------------|
| Deploy to staging | `sha-abc1234`, `staging` |
| Deploy to prod | `sha-abc1234`, `prod`, `latest` |

### Breaking Migrations

For migrations that require downtime (DROP TABLE, etc.):

**Option 1: PR Label**
1. Add `breaking-migration` label to your PR
2. Merge the PR
3. Workflow auto-detects and scales down before migrating

**Option 2: Manual**
1. Go to Actions → Build and Deploy to K8s
2. Click "Run workflow"
3. Check "Scale to zero for breaking DB migration"

### Deploy Flow

```
Manual Trigger
      │
      ├─► Check for breaking migration (label or checkbox)
      │
      ├─► Build multi-arch images (amd64 + arm64)
      │
      ├─► Push to ghcr.io
      │
      ├─► [If breaking] Scale down all pods
      │
      ├─► Deploy new images (kubectl set image)
      │
      ├─► Wait for API rollout
      │
      ├─► Run migrations (kubectl exec on NEW container)
      │
      ├─► Wait for worker/scheduler rollout
      │
      └─► [If breaking] Scale back up
```

### Reset Staging Flow

```
Manual Trigger
      │
      ├─► Get main branch migration revisions
      │
      ├─► Downgrade migrations not in main
      │
      ├─► Deploy :main image (no rebuild!)
      │
      ├─► Run migrations + seed
      │
      └─► Wait for rollout
```

---

## 5. On-Premise Installation (Customers)

### Docker Compose (Recommended)

```bash
# Pull images (public registry, no auth needed)
docker pull ghcr.io/scopeo/draftnrun-api:latest
docker pull ghcr.io/scopeo/draftnrun-worker:latest
docker pull ghcr.io/scopeo/draftnrun-scheduler:latest

# Create docker-compose.yml with your config
# Run
docker-compose up -d
```

### Required Environment Variables

Customers need to provide:

```env
# Database (they provide their own PostgreSQL)
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=ada
POSTGRES_USER=ada
POSTGRES_PASSWORD=...

# Redis
REDIS_URL=redis://localhost:6379

# AI Keys (they provide their own)
OPENAI_API_KEY=sk-...
```

### Minimum Requirements

- Docker 20.10+
- 4GB RAM
- 20GB disk
- PostgreSQL 14+
- Redis 6+

---

## 6. Useful Commands

### Check Pod Status

```bash
kubectl get pods -n ada-staging
kubectl get pods -n ada-prod
```

### View Logs

```bash
# API logs
kubectl logs -f deployment/ada-api -n ada-staging

# Worker logs
kubectl logs -f deployment/ada-worker -n ada-staging

# All pods
kubectl logs -f -l app=ada -n ada-staging
```

### Restart Deployments

```bash
kubectl rollout restart deployment -n ada-staging
```

### Run Migrations Manually

```bash
kubectl exec deployment/ada-api -n ada-staging -- \
  alembic -c ada_backend/database/alembic.ini upgrade head
```

### Check Current Migration

```bash
kubectl exec deployment/ada-api -n ada-staging -- \
  alembic -c ada_backend/database/alembic.ini current
```

### Scale Deployments

```bash
# Scale down
kubectl scale deployment ada-api -n ada-staging --replicas=0

# Scale up
kubectl scale deployment ada-api -n ada-staging --replicas=1
```

### SSH to EC2 (for debugging)

```bash
ssh -i your-key.pem ec2-user@<EC2_IP>
```

---

## 7. Troubleshooting

### Pod not starting

```bash
# Check events
kubectl describe pod <pod-name> -n ada-staging

# Check logs
kubectl logs <pod-name> -n ada-staging
```

### Image pull errors

```bash
# Check image exists
docker pull ghcr.io/scopeo/draftnrun-api:latest

# Images are public - no auth needed
```

### Migration failed

```bash
# Check current state
kubectl exec deployment/ada-api -n ada-staging -- \
  alembic -c ada_backend/database/alembic.ini current

# Downgrade one step
kubectl exec deployment/ada-api -n ada-staging -- \
  alembic -c ada_backend/database/alembic.ini downgrade -1
```

### K3s not responding

```bash
# On EC2
sudo systemctl status k3s
sudo systemctl restart k3s
sudo journalctl -u k3s -f
```

---

## 8. First-Time Setup Checklist

- [ ] Create EC2 instance for staging
- [ ] Create EC2 instance for prod (separate server)
- [ ] Install k3s on both EC2s
- [ ] Add `EC2_HOST_K8S_STAGING` secret to GitHub
- [ ] Add `EC2_HOST_K8S_PROD` secret to GitHub
- [ ] Create `credentials.env` on each EC2
- [ ] Apply secrets to K8s namespaces
- [ ] Run first deploy workflow
- [ ] Make ghcr.io packages public (Settings → Packages → each package → Visibility → Public)
