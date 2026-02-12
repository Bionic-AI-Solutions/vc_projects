# Gmail SMTP Relay Setup for Kubernetes

This document explains how to configure the Gmail SMTP relay service for sending emails from the VC Due Diligence application.

## Overview

The `gmail-relay` service acts as an SMTP relay that forwards emails through Gmail's SMTP relay infrastructure. This allows the VC tools application to send PDF reports via email.

## Architecture

```
VC Tools App → gmail-relay Service → smtp-relay.gmail.com → Recipients
```

- **VC Tools App**: Connects to `gmail-relay:25` (internal service)
- **gmail-relay Service**: Postfix SMTP relay that forwards to Gmail
- **Gmail SMTP Relay**: Google's smtp-relay.gmail.com:587

## Gmail SMTP Relay Configuration

### Option 1: Google Workspace SMTP Relay (Recommended)

If you have Google Workspace, you can use Gmail's SMTP relay service:

1. **Enable SMTP Relay in Google Admin Console**:
   - Go to: Apps → Google Workspace → Gmail → Routing
   - Configure SMTP relay service
   - Add your server's IP addresses to allowed IP ranges
   - Set allowed senders: `bionicaisolutions.com`

2. **Authentication Options**:
   - **IP-based (No Auth)**: Recommended if your cluster has static IPs
   - **Username/Password**: Use app-specific password if needed

3. **Configuration**:
   ```yaml
   RELAY_HOST: smtp-relay.gmail.com
   RELAY_PORT: 587
   ALLOWED_SENDER_DOMAINS: bionicaisolutions.com
   ```

### Option 2: Gmail with App Password

If using regular Gmail account:

1. **Enable 2-Factor Authentication** on your Gmail account

2. **Create App Password**:
   - Go to: Google Account → Security → 2-Step Verification → App passwords
   - Generate password for "Mail"

3. **Update Secret**:
   ```bash
   kubectl edit secret gmail-relay-secret -n vc-tools
   ```
   Add your credentials:
   ```yaml
   stringData:
     RELAY_USERNAME: "your-email@gmail.com"
     RELAY_PASSWORD: "your-app-password"
   ```

## Deployment

### 1. Deploy Gmail Relay Service

```bash
kubectl apply -f gmail-relay-deployment.yaml
```

This creates:
- **ConfigMap**: `gmail-relay-config` - SMTP configuration
- **Secret**: `gmail-relay-secret` - Credentials (if needed)
- **Deployment**: `gmail-relay` - Postfix SMTP relay
- **Service**: `gmail-relay` - ClusterIP service on port 25

### 2. Verify Deployment

```bash
# Check deployment status
kubectl get deployment gmail-relay -n vc-tools

# Check pods
kubectl get pods -l app=gmail-relay -n vc-tools

# Check service
kubectl get svc gmail-relay -n vc-tools

# View logs
kubectl logs -f deployment/gmail-relay -n vc-tools
```

### 3. Test SMTP Connection

From within a pod:

```bash
# Test telnet connection
kubectl run -it --rm test-smtp --image=alpine --restart=Never -- sh
apk add telnet
telnet gmail-relay 25

# Should see: 220 gmail-relay.vc-tools.svc.cluster.local ESMTP Postfix
```

## Configuration Files

### ConfigMap: gmail-relay-config

Edit if needed:

```bash
kubectl edit configmap gmail-relay-config -n vc-tools
```

Key settings:
- `RELAY_HOST`: Gmail SMTP server (smtp-relay.gmail.com)
- `RELAY_PORT`: Port (587 for TLS)
- `ALLOWED_SENDER_DOMAINS`: Your domain (bionicaisolutions.com)
- `RELAY_NETWORKS`: Kubernetes pod network (10.0.0.0/8)

### Secret: gmail-relay-secret

Update credentials if using authentication:

```bash
kubectl edit secret gmail-relay-secret -n vc-tools
```

```yaml
stringData:
  RELAY_USERNAME: "your-email@gmail.com"
  RELAY_PASSWORD: "your-app-password"
```

## Troubleshooting

### Check Relay Logs

```bash
kubectl logs -f deployment/gmail-relay -n vc-tools
```

Look for:
- Connection attempts from vc-tools app
- Relay status to Gmail
- Authentication errors
- Delivery status

### Common Issues

#### 1. Authentication Failed

**Error**: `SASL authentication failed`

**Solution**:
- Verify Google Workspace SMTP relay is enabled
- Check IP allowlist includes cluster IPs
- Or use app-specific password

#### 2. Connection Refused

**Error**: `Connection refused to gmail-relay:25`

**Solution**:
```bash
# Check service is running
kubectl get svc gmail-relay -n vc-tools

# Check pods are ready
kubectl get pods -l app=gmail-relay -n vc-tools
```

#### 3. Relay Access Denied

**Error**: `Relay access denied`

**Solution**:
- Check `ALLOWED_SENDER_DOMAINS` matches your from address
- Verify `RELAY_NETWORKS` includes pod network
- Check Gmail admin console SMTP relay settings

#### 4. TLS/SSL Errors

**Error**: `TLS negotiation failed`

**Solution**:
- Verify `RELAYHOST_TLS_LEVEL=encrypt` is set
- Check outbound port 587 is allowed
- Review firewall rules

### Test Email Sending

From vc-tools pod:

```bash
# Get pod name
kubectl get pods -l app=vc-tools -n vc-tools

# Exec into pod
kubectl exec -it <pod-name> -n vc-tools -- sh

# Test with Python
python3 << EOF
import smtplib
from email.mime.text import MIMEText

msg = MIMEText("Test email from VC Tools")
msg['Subject'] = 'Test Email'
msg['From'] = 'info@bionicaisolutions.com'
msg['To'] = 'your-email@example.com'

s = smtplib.SMTP('gmail-relay', 25)
s.send_message(msg)
s.quit()
print("Email sent!")
EOF
```

## Monitoring

### Check Email Queue

```bash
kubectl exec -it deployment/gmail-relay -n vc-tools -- mailq
```

### View Postfix Logs

```bash
kubectl logs -f deployment/gmail-relay -n vc-tools | grep -i "status="
```

Log patterns:
- `status=sent`: Email delivered successfully
- `status=deferred`: Temporary failure, will retry
- `status=bounced`: Permanent failure

### Email Metrics

```bash
# Count sent emails (last hour)
kubectl logs deployment/gmail-relay -n vc-tools --since=1h | grep "status=sent" | wc -l

# Check for errors
kubectl logs deployment/gmail-relay -n vc-tools --since=1h | grep -i "error\|reject\|fail"
```

## Security Best Practices

1. **Use IP-based authentication** when possible (Google Workspace)
2. **Limit sender domains** to your organization
3. **Restrict relay networks** to pod CIDR only
4. **Use TLS/STARTTLS** for all connections
5. **Monitor logs** for unauthorized relay attempts
6. **Rotate credentials** regularly if using password auth

## Gmail SMTP Relay Limits

**Google Workspace**:
- 10,000 emails per day per user
- 2,000 emails per day per alias
- 10,000 recipients per day

**Regular Gmail**:
- 500 emails per day
- 100 recipients per email

Plan your usage accordingly and implement rate limiting if needed.

## Alternative Configuration

### Using External SMTP Service

Instead of Gmail relay, you can use:

1. **SendGrid**: Update ConfigMap to point to `smtp.sendgrid.net:587`
2. **AWS SES**: Use `email-smtp.region.amazonaws.com:587`
3. **Mailgun**: Use `smtp.mailgun.org:587`

Update the ConfigMap accordingly:

```bash
kubectl edit configmap gmail-relay-config -n vc-tools
```

## Support

For issues:
1. Check logs: `kubectl logs -f deployment/gmail-relay -n vc-tools`
2. Verify configuration: `kubectl describe deployment gmail-relay -n vc-tools`
3. Test connectivity: Use telnet from test pod
4. Review Gmail admin console SMTP settings
