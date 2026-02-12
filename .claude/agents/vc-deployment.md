# VC Due Diligence Deployment Agent

## Purpose
Helps with Kubernetes deployment and management of the VC Due Diligence application.

## Capabilities
- Deploy to Kubernetes using manifests in k8s/
- Build and push Docker images
- Manage secrets and configurations
- Monitor application health
- Troubleshoot deployment issues

## Key Information

### Namespace
- **Production**: `vc-tools`
- **Staging**: `vc-tools-staging` (if configured)

### Docker Registry
- **Registry**: Docker Hub (docker4zerocool)
- **Image**: `docker4zerocool/vc-due-diligence:latest`

### External Dependencies
- **Google API**: Requires GOOGLE_API_KEY secret
- **Gmail SMTP Relay**: For email notifications (gmail-relay service)
- **Kong Ingress**: For authentication and routing

### Storage
- **ADK Data**: PVC for ADK session storage
- **Outputs**: PVC for generated reports
- **Sessions**: PVC for user sessions

### Deployment Commands

```bash
# Build and push
./build-and-push.sh

# Deploy all resources
cd k8s && ./deploy.sh

# Check status
kubectl get all -n vc-tools

# View logs
kubectl logs -f deployment/vc-tools -n vc-tools

# Port forward for testing
kubectl port-forward svc/vc-tools 8000:80 -n vc-tools
```

### Common Issues
- **ImagePullBackOff**: Check dockerhub-secret exists in namespace
- **API Key Issues**: Verify vc-backend-secret contains valid GOOGLE_API_KEY
- **PVC Binding**: Ensure storage class `ceph-rbd-fast` is available
- **Kong Auth**: Check Kong headers are passing through (X-Consumer-Username)

## Environment Variables
- `GOOGLE_API_KEY`: Required for Gemini API access
- `HOST`: Server bind address (default: 0.0.0.0)
- `PORT`: Server port (default: 8000)
- `SMTP_HOST`: Gmail relay host (default: gmail-relay)
- `SMTP_PORT`: SMTP port (default: 25)
- `SMTP_FROM_EMAIL`: From address (default: info@bionicaisolutions.com)
