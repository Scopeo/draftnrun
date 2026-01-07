#!/bin/bash
# Setup k3s (lightweight Kubernetes) on ARM EC2
# Run as root or with sudo

set -e

echo "=== k3s Setup for ARM EC2 ==="

# Check if running as root
if [[ $EUID -ne 0 ]]; then
   echo "This script must be run as root (sudo)"
   exit 1
fi

# Detect architecture
ARCH=$(uname -m)
echo "Detected architecture: $ARCH"

if [[ "$ARCH" != "aarch64" && "$ARCH" != "arm64" ]]; then
    echo "Warning: This script is optimized for ARM64, detected $ARCH"
fi

echo ""
echo "=== Step 1: Update system ==="
if command -v dnf &> /dev/null; then
    dnf update -y
elif command -v apt-get &> /dev/null; then
    apt-get update && apt-get upgrade -y
fi

echo ""
echo "=== Step 2: Install Docker ==="
if command -v docker &> /dev/null; then
    echo "Docker already installed"
    docker --version
else
    if command -v dnf &> /dev/null; then
        # Amazon Linux 2023
        dnf install -y docker
    elif command -v apt-get &> /dev/null; then
        # Ubuntu/Debian
        apt-get install -y docker.io
    fi
    systemctl enable --now docker
fi

# Add ec2-user to docker group
if id "ec2-user" &>/dev/null; then
    usermod -aG docker ec2-user
fi

echo ""
echo "=== Step 3: Install k3s ==="
if command -v k3s &> /dev/null; then
    echo "k3s already installed"
    k3s --version
else
    # Install k3s with readable kubeconfig
    curl -sfL https://get.k3s.io | sh -s - --write-kubeconfig-mode 644
fi

echo ""
echo "=== Step 4: Wait for k3s to be ready ==="
sleep 10
kubectl get nodes

echo ""
echo "=== Step 5: Install Helm ==="
if command -v helm &> /dev/null; then
    echo "Helm already installed"
    helm version
else
    curl https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash
fi

echo ""
echo "=== Step 6: Configure kubectl for ec2-user ==="
if id "ec2-user" &>/dev/null; then
    mkdir -p /home/ec2-user/.kube
    cp /etc/rancher/k3s/k3s.yaml /home/ec2-user/.kube/config
    chown -R ec2-user:ec2-user /home/ec2-user/.kube
    echo "export KUBECONFIG=/home/ec2-user/.kube/config" >> /home/ec2-user/.bashrc
fi

echo ""
echo "=== Setup Complete ==="
echo ""
echo "Next steps:"
echo "1. Log out and back in (for docker group)"
echo "2. Verify with: kubectl get nodes"
echo "3. Create namespace: kubectl apply -f infra/k8s/staging/namespace.yaml"
echo "4. Create secrets: kubectl create secret generic ada-secrets --from-env-file=.env -n ada-staging"
echo "5. Apply deployments: kubectl apply -f infra/k8s/staging/"
echo ""
echo "To get kubeconfig for GitHub Actions:"
echo "  cat /etc/rancher/k3s/k3s.yaml"
echo ""
echo "Remember to replace 127.0.0.1 with your EC2's public IP in the kubeconfig!"
