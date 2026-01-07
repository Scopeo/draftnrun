# K8s TODO / Technical Debt

## Critical: Worker Graceful Shutdown

- [ ] Add SIGTERM handler to ingestion worker
  - Currently if K8s restarts worker during ingestion:
    - Task is lost (partially completed)
    - No retry mechanism
  - Solutions:
    1. Add SIGTERM handler to worker
    2. Finish current task before exiting
    3. Or: re-queue task on shutdown
  - File: `ada_ingestion_system/worker/main.py`

## Critical: Migrate to K8s CronJob

- [ ] Replace APScheduler with K8s native CronJob
  - Current issue: Scheduler uses `Recreate` strategy, brief gap during deploys
  - K8s CronJob benefits:
    - Guaranteed execution (K8s handles scheduling)
    - No gap during deploys
    - Native K8s resource (better observability)
  - Migration steps:
    1. Create K8s CronJob manifests for each cron task
    2. CronJob triggers a Job that calls an API endpoint
    3. Or: CronJob runs a one-shot container
    4. Remove APScheduler dependency
  - Note: `misfire_grace_time: 300` is already set as interim solution

---

## Logging

- [ ] Centralize logging configuration
  - Currently `logging-config.yaml` is copied into each container
  - Should use ConfigMap to share logging config across all pods
  - Example:
    ```yaml
    apiVersion: v1
    kind: ConfigMap
    metadata:
      name: logging-config
    data:
      logging-config.yaml: |
        # logging config here
    ```
  - Then mount in deployments:
    ```yaml
    volumes:
      - name: logging-config
        configMap:
          name: logging-config
    volumeMounts:
      - name: logging-config
        mountPath: /app/logging-config.yaml
        subPath: logging-config.yaml
    ```

## Docker Images

- [ ] Consolidate WeasyPrint dependencies
  - API, scheduler, and worker all need the same system libs
  - Consider a shared base image to reduce duplication

## Future Improvements

- [ ] Add health checks for scheduler and worker
- [ ] Add resource monitoring (Prometheus metrics)
- [ ] Add HPA (Horizontal Pod Autoscaler) for API
- [ ] Migrate CI/CD from SSH to KUBECONFIG + Kustomize
  - Current: SSH to EC2 + kubectl commands
  - Better: Store KUBECONFIG as GitHub secret, use `kubectl apply -k`
  - Benefits:
    - No SSH access needed
    - Use `infra/k8s/` Kustomize overlays for env-specific config
    - More secure (no SSH keys in CI)
  - Files ready: `infra/k8s/base/`, `infra/k8s/staging/`, `infra/k8s/prod/`
