# Multi-stage build for AI VC Due Diligence Agent
FROM python:3.12-slim AS builder

# Install system dependencies for weasyprint and matplotlib
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    libcairo2 \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libgdk-pixbuf-2.0-0 \
    libffi-dev \
    shared-mime-info \
    libfreetype6-dev \
    libpng-dev \
    poppler-utils \
    && rm -rf /var/lib/apt/lists/*

# Create virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy requirements and install Python dependencies
COPY requirements.txt /tmp/
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r /tmp/requirements.txt

# Final stage
FROM python:3.12-slim

# Install runtime dependencies
RUN apt-get update && apt-get install -y \
    libcairo2 \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libgdk-pixbuf-2.0-0 \
    shared-mime-info \
    libfreetype6 \
    poppler-utils \
    && rm -rf /var/lib/apt/lists/*

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Set working directory
WORKDIR /app

# Copy application code
COPY vc_due_diligence/ /app/vc_due_diligence/
COPY requirements.txt /app/
COPY server.py /app/
COPY kong-proxy.py /app/

# Create _outputs directory (underscore prefix to avoid ADK treating it as agent)
RUN mkdir -p /app/vc_due_diligence/_outputs && \
    chmod 755 /app/vc_due_diligence/_outputs

# Create non-root user and fix ADK config permissions
RUN useradd -m -u 1000 appuser && \
    chown -R appuser:appuser /app && \
    mkdir -p /opt/venv/lib/python3.12/site-packages/google/adk/cli/browser/assets/config && \
    chmod -R 777 /opt/venv/lib/python3.12/site-packages/google/adk/cli/browser/assets/config && \
    chown -R appuser:appuser /opt/venv/lib/python3.12/site-packages/google/adk/cli/browser/assets/config
USER appuser

# Expose ADK web port
EXPOSE 8000

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health').read()" || exit 1

# Run ADK web server on port 8001 (proxy will listen on 8000)
# Run from /app so ADK discovers vc_due_diligence/ as an agent package
WORKDIR /app
CMD ["adk", "web", "--host", "0.0.0.0", "--port", "8001", "."]
