#!/usr/bin/env bash
set -e

echo "==> Installing CPU-only torch (avoids 1.8 GB GPU wheels)..."
pip install torch --index-url https://download.pytorch.org/whl/cpu --quiet

echo "==> Installing remaining dependencies..."
grep -v '^torch' requirements.txt | pip install -r /dev/stdin --quiet

echo "==> Build complete."
