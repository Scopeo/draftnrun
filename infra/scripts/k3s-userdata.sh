#!/bin/bash
# K3s User Data Script for EC2
# Reads Environment tag to configure staging/prod automatically
# Usage: Paste this into EC2 Launch Template user data
set -e

# Get instance metadata (IMDSv2)
TOKEN=$(curl -s -X PUT "http://169.254.169.254/latest/api/token" -H "X-aws-ec2-metadata-token-ttl-seconds: 21600")
INSTANCE_ID=$(curl -s -H "X-aws-ec2-metadata-token: $TOKEN" http://169.254.169.254/latest/meta-data/instance-id)
REGION=$(curl -s -H "X-aws-ec2-metadata-token: $TOKEN" http://169.254.169.254/latest/meta-data/placement/region)

# Get Environment tag (staging/prod)
ENV=$(aws ec2 describe-tags --region $REGION \
  --filters "Name=resource-id,Values=$INSTANCE_ID" "Name=key,Values=Environment" \
  --query "Tags[0].Value" --output text)

# Default to staging if not set
if [ "$ENV" == "None" ] || [ -z "$ENV" ]; then
  ENV="staging"
fi

NAMESPACE="ada-${ENV}"
IMAGE_TAG="${ENV}"  # staging or main
LOG_GROUP="/ada/${ENV}"

echo "========================================"
echo "Configuring K3s for: $ENV"
echo "Region: $REGION"
echo "Namespace: $NAMESPACE"
echo "========================================"

# Install dependencies
yum update -y
yum install -y docker git vim htop jq tree wget unzip

# Install k3s
curl -sfL https://get.k3s.io | sh -s - --write-kubeconfig-mode=644

# Wait for k3s to be ready
echo "Waiting for k3s to start..."
while ! /usr/local/bin/k3s kubectl get nodes &>/dev/null; do sleep 5; done
echo "K3s is ready!"

# Setup kubectl for ec2-user
mkdir -p /home/ec2-user/.kube
cp /etc/rancher/k3s/k3s.yaml /home/ec2-user/.kube/config
chown -R ec2-user:ec2-user /home/ec2-user/.kube
chmod 600 /home/ec2-user/.kube/config

# Add aliases and env vars
cat >> /home/ec2-user/.bashrc << 'BASHRC'
export KUBECONFIG=~/.kube/config
alias k=kubectl
alias kgp='kubectl get pods'
alias kgs='kubectl get svc'
alias kgd='kubectl get deployments'
alias klf='kubectl logs -f'
BASHRC

# Create namespace
/usr/local/bin/k3s kubectl create namespace $NAMESPACE || true

# Auto-deploy manifests (K3s watches /var/lib/rancher/k3s/server/manifests/)
cat > /var/lib/rancher/k3s/server/manifests/ada-deployments.yaml << MANIFEST
# Ada Deployments - Auto-deployed by K3s
apiVersion: apps/v1
kind: Deployment
metadata:
  name: ada-api
  namespace: $NAMESPACE
  labels:
    app: ada-api
spec:
  replicas: 1
  selector:
    matchLabels:
      app: ada-api
  template:
    metadata:
      labels:
        app: ada-api
    spec:
      containers:
        - name: ada-api
          image: ghcr.io/scopeo/draftnrun-api:$IMAGE_TAG
          imagePullPolicy: Always
          ports:
            - containerPort: 8000
          envFrom:
            - secretRef:
                name: ada-secrets
          resources:
            requests:
              memory: "512Mi"
              cpu: "250m"
            limits:
              memory: "2Gi"
              cpu: "1000m"
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
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: ada-worker
  namespace: $NAMESPACE
  labels:
    app: ada-worker
spec:
  replicas: 1
  selector:
    matchLabels:
      app: ada-worker
  template:
    metadata:
      labels:
        app: ada-worker
    spec:
      containers:
        - name: ada-worker
          image: ghcr.io/scopeo/draftnrun-worker:$IMAGE_TAG
          imagePullPolicy: Always
          envFrom:
            - secretRef:
                name: ada-secrets
          env:
            - name: MAX_CONCURRENT_INGESTIONS
              value: "2"
            - name: API_BASE_URL
              value: "http://ada-api"
            - name: ADA_URL
              value: "http://ada-api"
          resources:
            requests:
              memory: "512Mi"
              cpu: "250m"
            limits:
              memory: "4Gi"
              cpu: "2000m"
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: ada-scheduler
  namespace: $NAMESPACE
  labels:
    app: ada-scheduler
spec:
  replicas: 1
  strategy:
    type: Recreate
  selector:
    matchLabels:
      app: ada-scheduler
  template:
    metadata:
      labels:
        app: ada-scheduler
    spec:
      containers:
        - name: ada-scheduler
          image: ghcr.io/scopeo/draftnrun-scheduler:$IMAGE_TAG
          imagePullPolicy: Always
          envFrom:
            - secretRef:
                name: ada-secrets
          resources:
            requests:
              memory: "256Mi"
              cpu: "100m"
            limits:
              memory: "512Mi"
              cpu: "500m"
---
apiVersion: v1
kind: Service
metadata:
  name: ada-api
  namespace: $NAMESPACE
  labels:
    app: ada-api
spec:
  type: ClusterIP
  selector:
    app: ada-api
  ports:
    - port: 80
      targetPort: 8000
      protocol: TCP
---
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: ada-api
  namespace: $NAMESPACE
  annotations:
    traefik.ingress.kubernetes.io/router.entrypoints: web
spec:
  rules:
  - http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: ada-api
            port:
              number: 80
MANIFEST

# CloudWatch logging with Fluent Bit
cat > /var/lib/rancher/k3s/server/manifests/cloudwatch-logging.yaml << LOGGING
# CloudWatch Logging - Ships container logs to AWS CloudWatch
apiVersion: v1
kind: Namespace
metadata:
  name: amazon-cloudwatch
  labels:
    name: amazon-cloudwatch
---
apiVersion: v1
kind: ServiceAccount
metadata:
  name: fluent-bit
  namespace: amazon-cloudwatch
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: fluent-bit-role
rules:
  - apiGroups: [""]
    resources: [namespaces, pods, pods/logs]
    verbs: [get, list, watch]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: fluent-bit-role-binding
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: fluent-bit-role
subjects:
  - kind: ServiceAccount
    name: fluent-bit
    namespace: amazon-cloudwatch
---
apiVersion: v1
kind: ConfigMap
metadata:
  name: fluent-bit-config
  namespace: amazon-cloudwatch
data:
  fluent-bit.conf: |
    [SERVICE]
        Flush         5
        Log_Level     info
        Daemon        off
        Parsers_File  parsers.conf

    [INPUT]
        Name              tail
        Tag               kube.*
        Path              /var/log/containers/*${NAMESPACE}*.log
        Parser            docker
        DB                /var/log/flb_kube.db
        Mem_Buf_Limit     50MB
        Skip_Long_Lines   On
        Refresh_Interval  10

    [FILTER]
        Name                kubernetes
        Match               kube.*
        Kube_URL            https://kubernetes.default.svc:443
        Kube_CA_File        /var/run/secrets/kubernetes.io/serviceaccount/ca.crt
        Kube_Token_File     /var/run/secrets/kubernetes.io/serviceaccount/token
        Merge_Log           On
        Keep_Log            Off

    [OUTPUT]
        Name                cloudwatch_logs
        Match               *
        region              $REGION
        log_group_name      $LOG_GROUP
        log_stream_prefix   k8s-
        auto_create_group   true
        log_key             log

  parsers.conf: |
    [PARSER]
        Name        docker
        Format      json
        Time_Key    time
        Time_Format %Y-%m-%dT%H:%M:%S.%L
        Time_Keep   On
---
apiVersion: apps/v1
kind: DaemonSet
metadata:
  name: fluent-bit
  namespace: amazon-cloudwatch
  labels:
    k8s-app: fluent-bit
spec:
  selector:
    matchLabels:
      k8s-app: fluent-bit
  template:
    metadata:
      labels:
        k8s-app: fluent-bit
    spec:
      serviceAccountName: fluent-bit
      tolerations:
        - key: node-role.kubernetes.io/master
          operator: Exists
          effect: NoSchedule
      containers:
        - name: fluent-bit
          image: amazon/aws-for-fluent-bit:latest
          imagePullPolicy: Always
          env:
            - name: AWS_REGION
              value: "$REGION"
          resources:
            limits:
              memory: 200Mi
            requests:
              cpu: 100m
              memory: 100Mi
          volumeMounts:
            - name: varlog
              mountPath: /var/log
            - name: varlibdockercontainers
              mountPath: /var/lib/docker/containers
              readOnly: true
            - name: fluent-bit-config
              mountPath: /fluent-bit/etc/
      volumes:
        - name: varlog
          hostPath:
            path: /var/log
        - name: varlibdockercontainers
          hostPath:
            path: /var/lib/docker/containers
        - name: fluent-bit-config
          configMap:
            name: fluent-bit-config
LOGGING

echo ""
echo "========================================"
echo "K3s setup complete!"
echo "========================================"
echo "Environment: $ENV"
echo "Region: $REGION"
echo "Namespace: $NAMESPACE"
echo "CloudWatch Log Group: $LOG_GROUP"
echo ""
echo "Next steps:"
echo "1. SSH to this instance"
echo "2. Create credentials.env with your secrets"
echo "3. Run: kubectl create secret generic ada-secrets -n $NAMESPACE --from-env-file=credentials.env"
echo "4. Add this IP to GitHub secret EC2_HOST_K8S_${ENV^^}"
echo "========================================"
