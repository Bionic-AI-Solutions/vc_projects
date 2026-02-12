# Dev container Dockerfile for VC Due Diligence
FROM mcr.microsoft.com/devcontainers/python:3.12-bookworm

# Install system dependencies
RUN apt-get update && apt-get install -y \
    git \
    curl \
    wget \
    vim \
    && rm -rf /var/lib/apt/lists/*
