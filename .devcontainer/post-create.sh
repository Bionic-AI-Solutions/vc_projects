#!/bin/bash
set -e

echo "Setting up VC Due Diligence development environment..."

# Install Python dependencies
if [ -f requirements.txt ]; then
    echo "Installing Python dependencies..."
    pip install --no-cache-dir -r requirements.txt
fi

# Install Claude Code CLI and agent-browser (Node.js available via feature)
echo "Installing Claude Code CLI..."
npm install -g @anthropic-ai/claude-code || echo "Warning: Could not install Claude Code CLI"

echo "Installing agent-browser..."
npm install -g agent-browser || echo "Warning: Could not install agent-browser"

# Verify kubectl access
if [ -f ~/.kube/config ]; then
    echo "kubectl configuration found"
    kubectl version --client || echo "Warning: kubectl not fully configured"
else
    echo "Warning: No kubectl config found at ~/.kube/config"
fi

# Verify Docker access
if [ -S /var/run/docker.sock ]; then
    echo "Docker socket accessible"
    docker version || echo "Warning: Docker not fully accessible"
else
    echo "Warning: Docker socket not found"
fi

# Verify gh CLI
if command -v gh &> /dev/null; then
    echo "GitHub CLI (gh) installed"
else
    echo "Warning: gh CLI not found"
fi

echo ""
echo "✅ Development environment setup complete!"
echo ""
echo "Available tools:"
echo "  - Python $(python --version 2>&1 | cut -d' ' -f2)"
echo "  - Docker $(docker --version 2>&1 || echo 'not configured')"
echo "  - kubectl $(kubectl version --client --short 2>&1 || echo 'not configured')"
echo "  - gh $(gh --version 2>&1 | head -1 || echo 'not installed')"
echo "  - Claude Code CLI"
echo "  - agent-browser"
echo ""
echo "To start the VC Due Diligence agent:"
echo "  adk web"
echo ""
