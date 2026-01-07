# K8s Debugging Cheat Sheet

Quick reference for debugging the ada-staging deployment. No K8s experience required.

## Quick Setup

```bash
# Install k9s (visual UI - highly recommended)
brew install k9s        # Mac
# or
curl -sS https://webinstall.dev/k9s | bash  # Linux

# Then just run:
k9s -n ada-staging
```

K9s controls:
- Arrow keys to navigate
- `l` = view logs
- `d` = describe (why is it failing?)
- `s` = shell into container
- `/` = filter/search
- `q` = quit / go back

---

## View Logs

### Live logs (follow)
```bash
# API logs
kubectl logs -f deployment/ada-api -n ada-staging

# Worker logs (ingestion)
kubectl logs -f deployment/ada-worker -n ada-staging

# Scheduler logs (cron jobs)
kubectl logs -f deployment/ada-scheduler -n ada-staging
```

### Last 100 lines
```bash
kubectl logs deployment/ada-api -n ada-staging --tail=100
```

### Logs from crashed container
```bash
kubectl logs deployment/ada-api -n ada-staging --previous
```

### Logs from specific time
```bash
# Last hour
kubectl logs deployment/ada-api -n ada-staging --since=1h

# Last 30 minutes
kubectl logs deployment/ada-api -n ada-staging --since=30m
```

---

## Check Status

### Are pods running?
```bash
kubectl get pods -n ada-staging
```

Expected output:
```
NAME                            READY   STATUS    RESTARTS   AGE
ada-api-xxxxx-yyyyy             1/1     Running   0          1h
ada-api-xxxxx-zzzzz             1/1     Running   0          1h
ada-worker-xxxxx-yyyyy          1/1     Running   0          1h
ada-scheduler-xxxxx-yyyyy       1/1     Running   0          1h
```

### Why is a pod failing?
```bash
kubectl describe pod <POD_NAME> -n ada-staging
```
Look at the "Events" section at the bottom.

### Check all resources
```bash
kubectl get all -n ada-staging
```

---

## Common Problems

### Pod stuck in `CrashLoopBackOff`
The app is crashing on startup.

```bash
# See why it crashed
kubectl logs <POD_NAME> -n ada-staging --previous

# Check events
kubectl describe pod <POD_NAME> -n ada-staging
```

Common causes:
- Missing environment variable
- Database connection failed
- Invalid config

### Pod stuck in `Pending`
Not enough resources or node issues.

```bash
kubectl describe pod <POD_NAME> -n ada-staging
```

Look for:
- `Insufficient cpu`
- `Insufficient memory`
- `No nodes available`

### Pod stuck in `ImagePullBackOff`
Can't pull Docker image.

```bash
kubectl describe pod <POD_NAME> -n ada-staging
```

Common causes:
- Image doesn't exist (typo in tag?)
- Private registry auth failed
- Network issue

---

## Shell Into Container

```bash
# API container
kubectl exec -it deployment/ada-api -n ada-staging -- /bin/bash

# Worker container
kubectl exec -it deployment/ada-worker -n ada-staging -- /bin/bash

# Scheduler container
kubectl exec -it deployment/ada-scheduler -n ada-staging -- /bin/bash
```

Once inside, you can:
```bash
# Check environment variables
env | grep DATABASE

# Test database connection
python -c "from ada_backend.database.session import engine; print(engine.connect())"

# Check files
ls -la
```

---

## Restart Services

```bash
# Restart API (rolling restart - no downtime)
kubectl rollout restart deployment/ada-api -n ada-staging

# Restart worker
kubectl rollout restart deployment/ada-worker -n ada-staging

# Restart scheduler
kubectl rollout restart deployment/ada-scheduler -n ada-staging
```

---

## Rollback Deployment

If a deploy broke something:

```bash
# See deployment history
kubectl rollout history deployment/ada-api -n ada-staging

# Rollback to previous version
kubectl rollout undo deployment/ada-api -n ada-staging

# Rollback to specific revision
kubectl rollout undo deployment/ada-api -n ada-staging --to-revision=2
```

---

## View Secrets

```bash
# List secrets
kubectl get secrets -n ada-staging

# View secret values (base64 decoded)
kubectl get secret ada-secrets -n ada-staging -o jsonpath='{.data.DATABASE_URL}' | base64 -d
```

---

## CloudWatch Logs

Logs are shipped to AWS CloudWatch automatically.

### Setup (one-time)

1. Ensure your EC2 has an IAM role with CloudWatch permissions:
   ```json
   {
     "Version": "2012-10-17",
     "Statement": [{
       "Effect": "Allow",
       "Action": [
         "logs:CreateLogGroup",
         "logs:CreateLogStream",
         "logs:PutLogEvents",
         "logs:DescribeLogStreams"
       ],
       "Resource": "arn:aws:logs:*:*:log-group:/ada/*"
     }]
   }
   ```

2. Update the region in `cloudwatch-logging.yaml` (default: us-east-1)

3. Apply the config:
   ```bash
   kubectl apply -f infra/k8s/staging/cloudwatch-logging.yaml
   ```

### Viewing Logs in CloudWatch

1. Go to AWS Console → CloudWatch → Log Groups
2. Find `/ada/staging/<node-name>`
3. Use Log Insights for searching:
   ```
   fields @timestamp, @message
   | filter @message like /ada-api/
   | sort @timestamp desc
   | limit 100
   ```

### Useful CloudWatch Queries

```sql
# API errors
fields @timestamp, @message
| filter @message like /ERROR/
| filter @message like /ada-api/
| sort @timestamp desc

# Slow requests (over 5 seconds)
fields @timestamp, @message
| filter @message like /request completed/
| filter duration > 5000
| sort @timestamp desc

# Worker ingestion tasks
fields @timestamp, @message
| filter @message like /ada-worker/
| filter @message like /ingestion/
| sort @timestamp desc
```

---

## Useful Aliases

Add to your `~/.bashrc` or `~/.zshrc`:

```bash
alias k='kubectl'
alias kgs='kubectl get pods -n ada-staging'
alias klogs='kubectl logs -f -n ada-staging'

# Usage:
# kgs                           # list pods
# klogs deployment/ada-api      # follow API logs
```

---

## Emergency: Delete and Recreate Pod

If a pod is stuck and restart doesn't work:

```bash
# Delete the pod (K8s will auto-create a new one)
kubectl delete pod <POD_NAME> -n ada-staging
```

---

## Need More Help?

```bash
# Get help for any command
kubectl help
kubectl logs --help

# Explain any K8s resource
kubectl explain pod
kubectl explain deployment.spec.strategy
```
