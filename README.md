# AI VC Due Diligence Agent Team

A multi-agent AI pipeline for startup investment analysis, built with [Google ADK](https://google.github.io/adk-docs/) and Gemini 3 Pro/Flash. Deployed on Kubernetes with Kong authentication, per-user email delivery via Redis, and Gmail SMTP relay.

**Works with any startup** - from early-stage unknowns to well-funded companies. Just provide a company name, website URL, or both.

## Features

- **Live Research** - Real-time web search for company and market data
- **URL Support** - Analyze any startup by their website URL
- **Revenue Charts** - Bear/Base/Bull projection charts with matplotlib
- **Deep Risk Analysis** - Comprehensive risk assessment across 5 categories
- **Professional Reports** - McKinsey-style HTML investment reports
- **Comprehensive PDF** - Complete PDF report with all artifacts and agent outputs
- **Visual TL;DR** - AI-generated infographic summary for quick review
- **Per-User Email Delivery** - PDF reports emailed to the authenticated user via Kong + Redis
- **Multi-User Support** - Kong basic-auth with per-session email isolation

## Architecture Overview

```
Internet
    |
    v
┌─────────────────────────────────────────────────────────────────┐
│  Kong Ingress Controller (basic-auth + CORS)                     │
│  - Authenticates users via basic-auth                            │
│  - Adds X-Consumer-Username header to upstream requests          │
└──────────────────────────┬──────────────────────────────────────┘
                           |
                           v
┌─────────────────────────────────────────────────────────────────┐
│  vc-tools Pod (vc-tools namespace)                               │
│                                                                   │
│  ┌──────────────────┐         ┌──────────────────────────────┐   │
│  │  kong-proxy       │  :8000  │  vc-tools (ADK app)          │   │
│  │  (sidecar)        │────────>│  :8001                       │   │
│  │                   │         │                              │   │
│  │  Captures X-Con-  │         │  7-stage analysis pipeline   │   │
│  │  sumer-Username   │         │  PDF generation + email      │   │
│  │  Stores email in  │         │  Reads email from Redis      │   │
│  │  Redis by session │         │                              │   │
│  └──────────────────┘         └──────────────────────────────┘   │
│           |                              |                        │
└───────────┼──────────────────────────────┼───────────────────────┘
            |                              |
            v                              v
   ┌─────────────────┐          ┌─────────────────────┐
   │  Redis Cluster    │          │  Gmail SMTP Relay    │
   │  (redis ns)       │          │  (vc-tools ns)       │
   │  session_email:   │          │  smtp-relay.gmail.   │
   │  {session_id}     │          │  com:587             │
   └─────────────────┘          └─────────────────────┘
```

## What It Does

Given a startup name or URL, the pipeline automatically:

1. **Researches the company** - Founders, funding, product, traction
2. **Analyzes the market** - TAM/SAM, competitors, positioning
3. **Builds financial models** - Revenue projections, unit economics
4. **Assesses risks** - Market, execution, financial, regulatory, exit
5. **Generates investor memo** - Structured investment thesis
6. **Creates HTML report** - Professional due diligence document
7. **Generates comprehensive PDF** - Complete report emailed to authenticated user
8. **Generates infographic** - Visual summary for quick review

## Deployment

### Prerequisites

- Kubernetes cluster with Kong Ingress Controller
- Redis cluster (e.g., `redis-cluster.redis.svc.cluster.local:6379`)
- Google API key for Gemini models
- Google Workspace with SMTP relay configured
- Docker Hub access for image push

### Quick Deploy

```bash
# Clone
git clone https://github.com/Bionic-AI-Solutions/vc_projects.git
cd vc_projects

# Build and push Docker image
./build-and-push.sh

# Deploy to Kubernetes
kubectl apply -f k8s/namespace.yaml
kubectl apply -f k8s/configmap.yaml
kubectl apply -f k8s/secret.yaml          # Set GOOGLE_API_KEY here
kubectl apply -f k8s/pvc.yaml
kubectl apply -f k8s/deployment.yaml
kubectl apply -f k8s/service.yaml
kubectl apply -f k8s/ingress.yaml
kubectl apply -f k8s/kong-basic-auth.yaml
kubectl apply -f k8s/kong-sse-plugin.yaml
kubectl apply -f k8s/gmail-relay-deployment.yaml
```

### Environment Variables

| Variable | Container | Description |
|----------|-----------|-------------|
| `GOOGLE_API_KEY` | vc-tools | Gemini API key |
| `REDIS_HOST` | kong-proxy, vc-tools | Redis cluster hostname |
| `SMTP_HOST` | vc-tools | Gmail relay service name (`gmail-relay`) |
| `SMTP_PORT` | vc-tools | SMTP port (`25`) |
| `SMTP_FROM_EMAIL` | vc-tools | Sender address (`info@bionicaisolutions.com`) |
| `SMTP_USE_AUTH` | vc-tools | `false` (relay handles auth) |

### Local Development

```bash
# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Set API key
export GOOGLE_API_KEY=your_api_key

# Run with ADK web UI
adk web
```

Open `http://localhost:8000` and try:
- *"Analyze https://agno.com for Series A investment of $30-50M"*
- *"Research Genspark AI for its next funding round"*
- *"Analyze riskprofiler.io for Series B funding"*

## Per-User Email Flow

The system ensures each user receives their own PDF report, even in multi-user environments:

1. **Kong authenticates** the user via basic-auth and adds `X-Consumer-Username` header
2. **kong-proxy sidecar** intercepts the request, extracts the email and ADK session_id
3. **Redis stores** the mapping: `session_email:{session_id} -> user@email.com` (24h TTL)
4. **tools.py** retrieves the email from Redis using `tool_context.session.id` at PDF generation time
5. **Gmail relay** sends the PDF to the correct user via `smtp-relay.gmail.com:587`

### Key files

| File | Purpose |
|------|---------|
| `kong-proxy.py` | Sidecar proxy - captures Kong auth headers, stores email in Redis |
| `server.py` | Helper module - reads per-session email from Redis |
| `vc_due_diligence/tools.py` | Analysis tools - chart, report, PDF generation, email sending |
| `vc_due_diligence/agent.py` | Agent pipeline definition - 7 sequential stages |

## Pipeline Architecture

```
User Query: "Analyze https://agno.com for Series A"
    |
    v
┌─────────────────────────────────────────────────────────────────┐
│              DueDiligencePipeline (SequentialAgent)               │
│                                                                   │
│  ┌─────────────┐    ┌────────────────┐    ┌──────────────────┐   │
│  │  Stage 1     │    │    Stage 2     │    │     Stage 3      │   │
│  │  Company     │───>│    Market      │───>│    Financial     │   │
│  │  Research    │    │    Analysis    │    │    Modeling      │   │
│  └─────────────┘    └────────────────┘    └──────────────────┘   │
│         │                   │                      │              │
│         v                   v                      v              │
│  ┌─────────────┐    ┌────────────────┐    ┌──────────────────┐   │
│  │  Stage 4     │    │    Stage 5     │    │     Stage 6      │   │
│  │    Risk      │───>│   Investor     │───>│  HTML + PDF      │   │
│  │ Assessment   │    │     Memo       │    │    Generator     │   │
│  └─────────────┘    └────────────────┘    └──────────────────┘   │
│                                                    │              │
│                                                    v              │
│                                          ┌──────────────────┐    │
│                                          │     Stage 7       │    │
│                                          │   Infographic     │    │
│                                          │    Generator      │    │
│                                          └──────────────────┘    │
└─────────────────────────────────────────────────────────────────┘
    |
    v
Artifacts: revenue_chart.png, investment_report.html,
           comprehensive_report.pdf (emailed), infographic.jpg
```

## Agent Details

### Stage 1: Company Research Agent

| Property | Value |
|----------|-------|
| Model | `gemini-3-flash-preview` |
| Tools | `google_search` |
| Output Key | `company_info` |

Researches company basics, founders, product/technology, funding history, traction, and recent news.

### Stage 2: Market Analysis Agent

| Property | Value |
|----------|-------|
| Model | `gemini-3-flash-preview` |
| Tools | `google_search` |
| Output Key | `market_analysis` |

Analyzes market size (TAM/SAM), competitors, positioning, and trends.

### Stage 3: Financial Modeling Agent

| Property | Value |
|----------|-------|
| Model | `gemini-3-pro-preview` |
| Tools | `generate_financial_chart` |
| Output Key | `financial_model` |

Builds Bear/Base/Bull revenue projections and generates financial charts.

### Stage 4: Risk Assessment Agent

| Property | Value |
|----------|-------|
| Model | `gemini-3-pro-preview` |
| Tools | None (extended reasoning) |
| Output Key | `risk_assessment` |

Analyzes market, execution, financial, regulatory, and exit risks with severity ratings.

### Stage 5: Investor Memo Agent

| Property | Value |
|----------|-------|
| Model | `gemini-3-pro-preview` |
| Tools | None |
| Output Key | `investor_memo` |

Synthesizes all findings into a structured investment memo with recommendation.

### Stage 6: Report Generator Agent

| Property | Value |
|----------|-------|
| Model | `gemini-3-flash-preview` |
| Tools | `generate_html_report`, `generate_pdf_report` |
| Output Key | `report_results` |

Creates McKinsey-style HTML report and comprehensive 15-20 page PDF. The PDF is automatically emailed to the authenticated user.

### Stage 7: Infographic Generator Agent

| Property | Value |
|----------|-------|
| Model | `gemini-3-flash-preview` |
| Tools | `generate_infographic` (uses `gemini-3-pro-image-preview`) |
| Output Key | `infographic_result` |

Creates a visual summary infographic using AI image generation.

## Project Structure

```
vc_projects/
├── vc_due_diligence/
│   ├── __init__.py          # Exports root_agent
│   ├── agent.py             # 7-stage pipeline definition
│   └── tools.py             # Chart, report, PDF, email, infographic tools
├── kong-proxy.py            # Sidecar proxy for Kong header capture
├── server.py                # Redis-based email lookup helper
├── requirements.txt         # Python dependencies
├── Dockerfile               # Multi-stage build with WeasyPrint
├── build-and-push.sh        # Docker build and push script
├── k8s/
│   ├── deployment.yaml      # Pod with kong-proxy sidecar + vc-tools
│   ├── service.yaml         # ClusterIP service
│   ├── ingress.yaml         # Kong ingress with basic-auth + CORS
│   ├── kong-basic-auth.yaml # Kong consumers and credentials
│   ├── kong-sse-plugin.yaml # SSE support plugins
│   ├── gmail-relay-deployment.yaml  # Postfix relay to smtp-relay.gmail.com
│   ├── configmap.yaml       # App configuration
│   ├── secret.yaml          # API keys
│   ├── pvc.yaml             # Persistent volumes for outputs/sessions
│   ├── namespace.yaml       # vc-tools namespace
│   ├── hpa.yaml             # Horizontal pod autoscaler
│   └── kustomization.yaml   # Kustomize overlay
├── .devcontainer/           # VS Code dev container config
├── .claude/                 # Claude Code settings, skills, hooks
├── .cursor/                 # Cursor IDE rules and commands
└── .agents/                 # Agent skills (browser, skill-creator)
```

## Models Used

| Agent | Model | Why |
|-------|-------|-----|
| CompanyResearch | `gemini-3-flash-preview` | Fast web search |
| MarketAnalysis | `gemini-3-flash-preview` | Fast web search |
| FinancialModeling | `gemini-3-pro-preview` | Complex calculations |
| RiskAssessment | `gemini-3-pro-preview` | Deep reasoning |
| InvestorMemo | `gemini-3-pro-preview` | Synthesis quality |
| ReportGenerator | `gemini-3-flash-preview` | Fast HTML/PDF generation |
| InfographicGenerator | `gemini-3-flash-preview` | Orchestration |
| Infographic Tool | `gemini-3-pro-image-preview` | Image generation |

## Kong Authentication

Users are authenticated via Kong basic-auth. Consumer credentials are managed as Kubernetes secrets:

- **Sudhir**: `sudhir@fyda.net` (consumer in `vc-tools` namespace)
- **Salil**: `salil.kadam@bionicaisolutions.com` (consumer in `comfyui` namespace, Kong consumers are global)

To add a new user, create a KongConsumer and basic-auth credential Secret. See `k8s/kong-basic-auth.yaml` for examples.

## Gmail SMTP Relay

Email delivery uses a Postfix relay pod that forwards to Google Workspace SMTP relay:

- **Internal**: vc-tools connects to `gmail-relay:25` (no auth needed)
- **External**: Postfix relays to `[smtp-relay.gmail.com]:587` with STARTTLS
- **Sender**: `info@bionicaisolutions.com` (must match Workspace allowed sender domain)
- **IPv4 only**: Forced via `POSTFIX_inet_protocols=ipv4` (cluster has no IPv6 route)

## Learn More

- [Google ADK Documentation](https://google.github.io/adk-docs/)
- [Kong Ingress Controller](https://docs.konghq.com/kubernetes-ingress-controller/)
- [Gemini API](https://ai.google.dev/gemini-api/docs)
