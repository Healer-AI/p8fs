# EEPIS Website Deployment Guide

## Overview

The EEPIS landing page (www.eepis.ai) is served from the p8fs-api container using FastAPI's static file serving capabilities.

## Architecture

```
┌─────────────────────┐
│   www.eepis.ai      │
│   (NGINX Ingress)   │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│  ClusterIP Service  │
│   (port 80)         │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│  p8fs-eco:latest    │
│  (1 tiny pod)       │
│  256Mi RAM          │
│  100m CPU           │
└─────────────────────┘
           │
           ▼
┌─────────────────────┐
│  Static Files       │
│  /static/www/       │
│  - index-v3.html    │
│  - CSS, assets      │
└─────────────────────┘
```

## File Locations

### Static Files
```
p8fs-api/src/p8fs_api/static/www/
├── index-v3.html       # Main landing page
├── index-v1.html       # Alternative version
├── about.html
├── contact.html
├── login.html
├── privacy.html
├── terms.html
├── css/
│   ├── common.css
│   ├── style-v3.css
│   └── pages.css
└── assets/
    └── images/
        ├── logo.png
        └── logo-icon.png
```

### FastAPI Integration
File: `p8fs-api/src/p8fs_api/main.py`

```python
# Serves index-v3.html at /
@app.get("/", include_in_schema=False)
async def serve_landing_page():
    index_file = static_dir / "index-v3.html"
    return FileResponse(str(index_file))

# Serves any HTML page at /{page}.html
@app.get("/{page}.html", include_in_schema=False)
async def serve_html_pages(page: str):
    html_file = static_dir / f"{page}.html"
    return FileResponse(str(html_file))

# Static assets at /static/*
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
```

## Kubernetes Deployment

### Manifests
File: `p8fs-api/k8s/www-eepis.yaml`

Contains:
1. **Deployment** - Single pod running p8fs-eco:latest
2. **Service** - ClusterIP exposing port 80
3. **Ingress** - NGINX with TLS for www.eepis.ai and eepis.ai

### Deploy

```bash
# Apply manifests
kubectl apply -f p8fs-api/k8s/www-eepis.yaml

# Check status
kubectl get deployment www-eepis
kubectl get service www-eepis
kubectl get ingress www-eepis

# View logs
kubectl logs -l app=www-eepis -f
```

## Docker Image

The static files are included in the standard p8fs-eco image build:

```dockerfile
# Dockerfile already copies entire src directory
COPY p8fs-api/src ./p8fs-api/src
```

This includes `src/p8fs_api/static/www/` automatically.

### Build and Push

```bash
# Build multi-platform image
docker buildx build --platform linux/amd64,linux/arm64 \
  -t percolationlabs/p8fs-eco:latest --push .
```

## Local Development

### Run API Server

```bash
cd p8fs-api
uv run uvicorn src.p8fs_api.main:app --reload --host 0.0.0.0 --port 8000
```

Visit:
- http://localhost:8000/ - Landing page
- http://localhost:8000/about.html
- http://localhost:8000/static/css/common.css

### Update Static Files

1. Edit files in `p8fs-api/src/p8fs_api/static/www/`
2. Refresh browser (with `--reload` flag, changes are live)

## DNS Configuration

Point DNS records to ingress IP:

```bash
# Get ingress IP
kubectl get ingress www-eepis -o jsonpath='{.status.loadBalancer.ingress[0].ip}'
```

Create A records:
- `www.eepis.ai` → INGRESS_IP
- `eepis.ai` → INGRESS_IP

## TLS Certificates

Automatic via cert-manager with Let's Encrypt:

```yaml
annotations:
  cert-manager.io/cluster-issuer: letsencrypt-prod
tls:
- hosts:
  - www.eepis.ai
  - eepis.ai
  secretName: www-eepis-tls
```

Check status:
```bash
kubectl get certificate www-eepis-tls
kubectl describe certificate www-eepis-tls
```

## Updating the Website

### Option 1: Edit Static Files

```bash
# 1. Edit files locally
vim p8fs-api/src/p8fs_api/static/www/index-v3.html

# 2. Rebuild and push image
docker buildx build --platform linux/amd64,linux/arm64 \
  -t percolationlabs/p8fs-eco:latest --push .

# 3. Restart pods to pull new image
kubectl rollout restart deployment www-eepis

# 4. Monitor rollout
kubectl rollout status deployment www-eepis
```

### Option 2: Use Tags for Safer Deploys

```bash
# 1. Build with version tag
docker buildx build --platform linux/amd64,linux/arm64 \
  -t percolationlabs/p8fs-eco:v1.2.0 --push .

# 2. Update deployment
kubectl set image deployment/www-eepis \
  www-eepis=percolationlabs/p8fs-eco:v1.2.0

# 3. Rollback if needed
kubectl rollout undo deployment www-eepis
```

## Resource Configuration

Minimal resources for static site serving:

```yaml
resources:
  requests:
    memory: "256Mi"
    cpu: "100m"
  limits:
    memory: "512Mi"
    cpu: "500m"
```

## Health Checks

The API includes health endpoints:

- `/health` - General health check
- `/health/live` - Liveness probe (pod restart if fails)
- `/health/ready` - Readiness probe (traffic routing)

## Troubleshooting

### 404 Errors

```bash
# Check if static directory exists
kubectl exec -it deployment/www-eepis -- ls -la /app/p8fs-api/src/p8fs_api/static/www/

# Test internally
kubectl exec -it deployment/www-eepis -- curl http://localhost:8000/
```

### CSS/Assets Not Loading

Check browser console. Assets should load from:
- `/static/css/common.css`
- `/static/css/style-v3.css`
- `/static/assets/images/logo.png`

If 404, verify mount path in code matches file location.

### Ingress Issues

```bash
# Check ingress controller logs
kubectl logs -n ingress-nginx -l app.kubernetes.io/component=controller --tail=100

# Verify ingress configuration
kubectl describe ingress www-eepis
```

## Monitoring

### View Logs

```bash
# Follow logs
kubectl logs -l app=www-eepis -f

# Filter for errors
kubectl logs -l app=www-eepis | grep -i error

# Last 100 lines
kubectl logs -l app=www-eepis --tail=100
```

### Check Metrics

```bash
# Pod resource usage
kubectl top pod -l app=www-eepis

# Deployment status
kubectl get deployment www-eepis -o wide
```

## Security

- **Auth Disabled**: `P8FS_AUTH_DISABLED=true` for static site
- **TLS Required**: Ingress forces HTTPS redirect
- **Security Headers**: Added by FastAPI middleware
- **Non-Root User**: Container runs as `p8fs` user

## Backup Strategy

Static files are version-controlled in git:
- `p8fs-api/src/p8fs_api/static/www/`

To backup:
```bash
git commit -am "Update website content"
git push
```

## Production Checklist

- [x] Static files copied to p8fs-api/src/p8fs_api/static/www/
- [x] FastAPI routes configured in main.py
- [x] Dockerfile includes static files (via src/ copy)
- [x] Kubernetes manifests created
- [x] Health checks configured
- [ ] DNS records pointed to ingress
- [ ] TLS certificates provisioned
- [ ] Deployment tested
- [ ] Monitoring configured
- [ ] Rollback procedure tested
