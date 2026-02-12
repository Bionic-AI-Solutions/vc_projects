#!/bin/bash
set -e

# Configuration
IMAGE_NAME="docker4zerocool/vc-due-diligence"
VERSION=${1:-latest}
PLATFORMS="linux/amd64,linux/arm64"

echo "========================================="
echo "Building and Pushing VC Due Diligence Docker Image"
echo "========================================="
echo ""
echo "Image: $IMAGE_NAME:$VERSION"
echo "Platforms: $PLATFORMS"
echo ""

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
    echo "❌ Error: Docker is not running"
    exit 1
fi

# Check if logged in to Docker Hub
if ! docker info 2>&1 | grep -q "Username: docker4zerocool"; then
    echo "⚠️  Warning: Not logged in to Docker Hub as docker4zerocool"
    echo "Attempting to use existing credentials..."
fi

# Build for multiple platforms (optional - remove if not needed)
echo "🔨 Building Docker image..."
docker buildx create --use --name vc-builder 2>/dev/null || docker buildx use vc-builder

# Option 1: Multi-platform build (requires buildx)
# docker buildx build \
#     --platform $PLATFORMS \
#     --tag $IMAGE_NAME:$VERSION \
#     --tag $IMAGE_NAME:latest \
#     --push \
#     .

# Option 2: Single platform build (faster for testing)
docker build \
    --tag $IMAGE_NAME:$VERSION \
    --tag $IMAGE_NAME:latest \
    --file Dockerfile \
    .

if [ $? -eq 0 ]; then
    echo "✅ Build successful"
else
    echo "❌ Build failed"
    exit 1
fi

# Push to Docker Hub
echo ""
echo "📤 Pushing image to Docker Hub..."
docker push $IMAGE_NAME:$VERSION

if [ "$VERSION" != "latest" ]; then
    docker push $IMAGE_NAME:latest
fi

if [ $? -eq 0 ]; then
    echo "✅ Push successful"
else
    echo "❌ Push failed"
    exit 1
fi

echo ""
echo "========================================="
echo "✅ Docker image published successfully!"
echo "========================================="
echo ""
echo "Image: $IMAGE_NAME:$VERSION"
echo ""
echo "Next steps:"
echo "1. Update k8s/secret.yaml with your Google API Key"
echo "2. Create Docker registry secret in Kubernetes"
echo "3. Deploy to Kubernetes:"
echo "   kubectl apply -f k8s/"
echo ""
