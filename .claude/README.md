# Claude Configuration for VC Due Diligence

This directory contains Claude Code project-specific configuration.

## Structure

```
.claude/
├── agents/              # Custom agent configurations
│   └── vc-deployment.md # Kubernetes deployment helper agent
├── hooks/               # Automation hooks
│   ├── skill-activation-prompt.sh
│   └── post-tool-use-tracker.sh
├── skills/              # Custom Claude skills
│   ├── skill-developer/
│   └── backend-dev-guidelines/
├── settings.json        # Project settings
└── README.md           # This file
```

## Settings Overview

### Permissions
Pre-approved commands for faster development:
- File operations: find, rg, grep, ls, cat, head, tail
- Container tools: kubectl, docker
- Development: python, pip, adk, uvicorn
- Version control: gh

### MCP Servers
- **Enabled**: All project MCP servers
- **Active**: sequential-thinking

### Hooks
- **UserPromptSubmit**: Activates relevant skills based on user input
- **PostToolUse**: Tracks file modifications (Edit/Write operations)

## Skills Available

The agent-browser skill is installed in the devcontainer and can be activated when needed for browser automation tasks.

### Built-in Skills
- **skill-developer**: For creating new Claude skills
- **backend-dev-guidelines**: Python/backend development patterns

## Custom Agents

### vc-deployment
Specialized agent for Kubernetes deployment tasks. Invoke with:
```
@vc-deployment help me deploy to staging
```

Knows about:
- K8s manifests structure
- Docker build/push process
- PVC and secret management
- Common deployment issues

## Usage

Claude Code will automatically load these settings when working in this project. Skills can be invoked with slash commands or @ mentions.
