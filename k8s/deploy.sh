#!/bin/bash
set -e

echo "========================================="
echo "VC Due Diligence - Kubernetes Deployment"
echo "========================================="
echo ""

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if kubectl is installed
if ! command -v kubectl &> /dev/null; then
    echo -e "${RED}Error: kubectl is not installed${NC}"
    exit 1
fi

# Check if connected to cluster
if ! kubectl cluster-info &> /dev/null; then
    echo -e "${RED}Error: Not connected to a Kubernetes cluster${NC}"
    exit 1
fi

echo -e "${GREEN}✓ kubectl installed and connected to cluster${NC}"
echo ""

# Prompt for Docker Hub credentials
echo "Docker Hub Configuration"
echo "------------------------"
read -p "Enter Docker Hub username (default: docker4zerocool): " DOCKER_USERNAME
DOCKER_USERNAME=${DOCKER_USERNAME:-docker4zerocool}

read -sp "Enter Docker Hub password: " DOCKER_PASSWORD
echo ""
read -p "Enter Docker Hub email: " DOCKER_EMAIL
echo ""

# Prompt for Google API Key
echo "Google API Configuration"
echo "------------------------"
read -sp "Enter Google API Key: " GOOGLE_API_KEY
echo ""
echo ""

# Confirm deployment
echo "Deployment Summary"
echo "------------------"
echo "Namespace: vc-tools"
echo "Docker Username: $DOCKER_USERNAME"
echo "Docker Email: $DOCKER_EMAIL"
echo "Google API Key: ${GOOGLE_API_KEY:0:10}...${GOOGLE_API_KEY: -4}"
echo ""
read -p "Continue with deployment? (y/n): " CONFIRM

if [[ $CONFIRM != "y" && $CONFIRM != "Y" ]]; then
    echo "Deployment cancelled"
    exit 0
fi

echo ""
echo -e "${YELLOW}Starting deployment...${NC}"
echo ""

# Step 1: Create namespace
echo "1. Creating namespace..."
kubectl apply -f namespace.yaml
echo -e "${GREEN}✓ Namespace created${NC}"
echo ""

# Step 2: Create Docker registry secret
echo "2. Creating Docker registry secret..."
kubectl create secret docker-registry dockerhub-secret \
  --docker-server=https://index.docker.io/v1/ \
  --docker-username=$DOCKER_USERNAME \
  --docker-password=$DOCKER_PASSWORD \
  --docker-email=$DOCKER_EMAIL \
  --namespace=vc-tools \
  --dry-run=client -o yaml | kubectl apply -f -
echo -e "${GREEN}✓ Docker secret created${NC}"
echo ""

# Step 3: Create Google API secret
echo "3. Creating Google API secret..."
kubectl create secret generic vc-backend-secret \
  --from-literal=GOOGLE_API_KEY=$GOOGLE_API_KEY \
  --namespace=vc-tools \
  --dry-run=client -o yaml | kubectl apply -f -
echo -e "${GREEN}✓ API secret created${NC}"
echo ""

# Step 4: Create ConfigMap
echo "4. Creating ConfigMap..."
kubectl apply -f configmap.yaml
echo -e "${GREEN}✓ ConfigMap created${NC}"
echo ""

# Step 5: Create PersistentVolumeClaims
echo "5. Creating PersistentVolumeClaims..."
kubectl apply -f pvc.yaml
echo -e "${GREEN}✓ PVCs created${NC}"
echo ""

# Step 6: Wait for PVCs to be bound
echo "6. Waiting for PVCs to be bound..."
kubectl wait --for=condition=bound pvc/vc-tools-adk-data -n vc-tools --timeout=120s || echo -e "${YELLOW}Warning: PVC not bound yet, continuing...${NC}"
kubectl wait --for=condition=bound pvc/vc-tools-outputs -n vc-tools --timeout=120s || echo -e "${YELLOW}Warning: PVC not bound yet, continuing...${NC}"
kubectl wait --for=condition=bound pvc/vc-tools-sessions -n vc-tools --timeout=120s || echo -e "${YELLOW}Warning: PVC not bound yet, continuing...${NC}"
echo ""

# Step 6a: Deploy Gmail SMTP Relay
echo "6a. Deploying Gmail SMTP Relay service..."
kubectl apply -f gmail-relay-deployment.yaml
echo -e "${GREEN}✓ Gmail relay deployed${NC}"
echo ""

# Step 6b: Wait for Gmail relay to be ready
echo "6b. Waiting for Gmail relay to be ready..."
kubectl rollout status deployment/gmail-relay -n vc-tools --timeout=120s || echo -e "${YELLOW}Warning: Gmail relay not ready yet, continuing...${NC}"
echo ""

# Step 7: Deploy application
echo "7. Deploying application..."
kubectl apply -f deployment.yaml
echo -e "${GREEN}✓ Deployment created${NC}"
echo ""

# Step 8: Create service
echo "8. Creating service..."
kubectl apply -f service.yaml
echo -e "${GREEN}✓ Service created${NC}"
echo ""

# Step 9: Create HPA (optional)
echo "9. Creating HorizontalPodAutoscaler..."
kubectl apply -f hpa.yaml || echo -e "${YELLOW}Warning: HPA creation failed (metrics-server might not be installed)${NC}"
echo ""

# Step 10: Wait for deployment
echo "10. Waiting for deployment to be ready..."
kubectl rollout status deployment/vc-tools -n vc-tools --timeout=300s
echo -e "${GREEN}✓ Deployment ready${NC}"
echo ""

# Display status
echo ""
echo -e "${GREEN}=========================================${NC}"
echo -e "${GREEN}Deployment Complete!${NC}"
echo -e "${GREEN}=========================================${NC}"
echo ""
echo "Deployment Status:"
kubectl get deployment -n vc-tools
echo ""
echo "Pod Status:"
kubectl get pods -n vc-tools
echo ""
echo "Service Status:"
kubectl get svc -n vc-tools
echo ""
echo "PVC Status:"
kubectl get pvc -n vc-tools
echo ""

# Get service endpoint
SERVICE_TYPE=$(kubectl get svc vc-tools -n vc-tools -o jsonpath='{.spec.type}')
if [ "$SERVICE_TYPE" == "LoadBalancer" ]; then
    echo "Waiting for LoadBalancer IP..."
    kubectl get svc vc-tools -n vc-tools --watch &
    WATCH_PID=$!
    sleep 10
    kill $WATCH_PID 2>/dev/null || true
    
    EXTERNAL_IP=$(kubectl get svc vc-tools -n vc-tools -o jsonpath='{.status.loadBalancer.ingress[0].ip}')
    EXTERNAL_HOSTNAME=$(kubectl get svc vc-tools -n vc-tools -o jsonpath='{.status.loadBalancer.ingress[0].hostname}')
    
    if [ -n "$EXTERNAL_IP" ]; then
        echo -e "${GREEN}Access your application at: http://$EXTERNAL_IP${NC}"
    elif [ -n "$EXTERNAL_HOSTNAME" ]; then
        echo -e "${GREEN}Access your application at: http://$EXTERNAL_HOSTNAME${NC}"
    else
        echo -e "${YELLOW}LoadBalancer is still provisioning. Check status with: kubectl get svc -n vc-tools${NC}"
    fi
else
    echo "To access locally, run:"
    echo "  kubectl port-forward svc/vc-tools 8000:80 -n vc-tools"
    echo "Then open: http://localhost:8000"
fi

echo ""
echo "To view logs:"
echo "  kubectl logs -f deployment/vc-tools -n vc-tools"
echo ""
echo "To delete the deployment:"
echo "  kubectl delete namespace vc-tools"
echo ""
