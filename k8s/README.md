# Kubernetes Deployment Guide

This directory contains Kubernetes manifests for deploying the AI VC Due Diligence Agent.

## Prerequisites

- Kubernetes cluster (v1.24+)
- kubectl configured
- Docker Hub account (docker4zerocool)
- Google API Key from [Google AI Studio](https://aistudio.google.com/app/apikey)

## Quick Deploy

### 1. Create Docker Registry Secret

```bash
kubectl create secret docker-registry dockerhub-secret \
  --docker-server=https://index.docker.io/v1/ \
  --docker-username=docker4zerocool \
  --docker-password=YOUR_DOCKER_PASSWORD \
  --docker-email=YOUR_EMAIL \
  --namespace=vc-due-diligence
```

### 2. Update Google API Key

Edit `secret.yaml` and replace `YOUR_GOOGLE_API_KEY_HERE` with your actual key:

```yaml
stringData:
  GOOGLE_API_KEY: "your-actual-api-key-here"
```

### 3. Deploy All Resources

```bash
# Create namespace
kubectl apply -f namespace.yaml

# Create secrets (update secret.yaml first!)
kubectl apply -f secret.yaml

# Create configmap
kubectl apply -f configmap.yaml

# Create deployment
kubectl apply -f deployment.yaml

# Create service
kubectl apply -f service.yaml

# (Optional) Create ingress
kubectl apply -f ingress.yaml

# (Optional) Create HPA for auto-scaling
kubectl apply -f hpa.yaml
```

Or deploy everything at once:

```bash
kubectl apply -f .
```

## Verify Deployment

```bash
# Check pods
kubectl get pods -n vc-due-diligence

# Check service
kubectl get svc -n vc-due-diligence

# Check logs
kubectl logs -f deployment/vc-due-diligence -n vc-due-diligence

# Port forward for local access
kubectl port-forward svc/vc-due-diligence 8000:80 -n vc-due-diligence
```

Access the application at `http://localhost:8000`

## Manifests Overview

| File | Description |
|------|-------------|
| `namespace.yaml` | Creates the vc-due-diligence namespace |
| `secret.yaml` | Contains Google API key and Docker registry credentials |
| `configmap.yaml` | Application configuration settings |
| `deployment.yaml` | Main application deployment (2 replicas) |
| `service.yaml` | LoadBalancer service for external access |
| `ingress.yaml` | Ingress for domain-based routing (optional) |
| `hpa.yaml` | Horizontal Pod Autoscaler (2-10 replicas) |

## Configuration

### Scaling

The deployment includes:
- **Default**: 2 replicas
- **Auto-scaling**: 2-10 replicas based on CPU/memory usage
- **Resources**: 512Mi-2Gi memory, 250m-1000m CPU per pod

To manually scale:
```bash
kubectl scale deployment/vc-due-diligence --replicas=5 -n vc-due-diligence
```

### Updating the Image

```bash
# Update deployment with new image
kubectl set image deployment/vc-due-diligence \
  vc-due-diligence=docker4zerocool/vc-due-diligence:v2.0 \
  -n vc-due-diligence

# Check rollout status
kubectl rollout status deployment/vc-due-diligence -n vc-due-diligence

# Rollback if needed
kubectl rollout undo deployment/vc-due-diligence -n vc-due-diligence
```

### Environment Variables

Update `secret.yaml` or `configmap.yaml` and apply:

```bash
kubectl apply -f secret.yaml
kubectl apply -f configmap.yaml

# Restart pods to pick up changes
kubectl rollout restart deployment/vc-due-diligence -n vc-due-diligence
```

## Ingress Setup

### For Nginx Ingress Controller

1. Install Nginx Ingress Controller:
```bash
kubectl apply -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/main/deploy/static/provider/cloud/deploy.yaml
```

2. Update `ingress.yaml` with your domain:
```yaml
host: vc-due-diligence.yourdomain.com
```

3. Apply ingress:
```bash
kubectl apply -f ingress.yaml
```

### For AWS ALB

Uncomment AWS ALB annotations in `ingress.yaml` and apply.

### For GKE

Uncomment GKE annotations in `ingress.yaml` and apply.

## SSL/TLS Setup with Cert Manager

1. Install cert-manager:
```bash
kubectl apply -f https://github.com/cert-manager/cert-manager/releases/download/v1.13.0/cert-manager.yaml
```

2. Create ClusterIssuer:
```bash
cat <<EOF | kubectl apply -f -
apiVersion: cert-manager.io/v1
kind: ClusterIssuer
metadata:
  name: letsencrypt-prod
spec:
  acme:
    server: https://acme-v02.api.letsencrypt.org/directory
    email: your-email@example.com
    privateKeySecretRef:
      name: letsencrypt-prod
    solvers:
    - http01:
        ingress:
          class: nginx
EOF
```

3. Uncomment TLS section in `ingress.yaml` and apply.

## Monitoring

### Logs

```bash
# All pods
kubectl logs -l app=vc-due-diligence -n vc-due-diligence --tail=100 -f

# Specific pod
kubectl logs vc-due-diligence-xxxxx-xxxxx -n vc-due-diligence
```

### Events

```bash
kubectl get events -n vc-due-diligence --sort-by='.lastTimestamp'
```

### Resource Usage

```bash
kubectl top pods -n vc-due-diligence
kubectl top nodes
```

## Troubleshooting

### Pods not starting

```bash
# Check pod status
kubectl describe pod <pod-name> -n vc-due-diligence

# Check events
kubectl get events -n vc-due-diligence

# Check image pull
kubectl get pods -n vc-due-diligence -o jsonpath='{.items[*].status.containerStatuses[*].state}'
```

### ImagePullBackOff

Ensure Docker registry secret is created correctly:
```bash
kubectl get secret dockerhub-secret -n vc-due-diligence -o yaml
```

### API Key Issues

Check secret:
```bash
kubectl get secret vc-due-diligence-secrets -n vc-due-diligence -o yaml
```

## Cleanup

Remove all resources:

```bash
kubectl delete namespace vc-due-diligence
```

Or remove specific resources:

```bash
kubectl delete -f .
```

## Production Considerations

1. **Persistent Storage**: Consider using PersistentVolumeClaims for outputs
2. **Resource Limits**: Adjust based on actual usage
3. **Monitoring**: Integrate with Prometheus/Grafana
4. **Logging**: Use centralized logging (ELK, Loki, etc.)
5. **Security**: Use NetworkPolicies, PodSecurityPolicies
6. **Backup**: Regular backups of configuration and secrets
7. **High Availability**: Use pod anti-affinity for multi-zone deployment

## Support

For issues or questions, refer to the main project README.
