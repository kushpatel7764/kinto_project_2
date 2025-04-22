#!/bin/bash
set -euxo pipefail  # Enable debugging, error handling, and pipeline fail detection

# Read VERSION and clean up any CRLF characters
VERSION=$(cat kinto/plugins/admin/VERSION | tr -d '\r')
TAG="v${VERSION}"

# Download and unzip the release
echo "Downloading Kinto Admin version ${TAG}..."
curl -OL "https://github.com/Kinto/kinto-admin/releases/download/${TAG}/kinto-admin-release.tar"

# Remove old build directory if it exists, then create a new one
rm -rf ./kinto/plugins/admin/build || echo "admin/build folder doesn't exist yet"
mkdir -p ./kinto/plugins/admin/build

# Extract the tar file and clean up
tar -xf kinto-admin-release.tar -C ./kinto/plugins/admin/build && rm kinto-admin-release.tar
echo "$VERSION" > ./kinto/plugins/admin/build/VERSION  # Version info saved