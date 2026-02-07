#!/bin/bash
# Post-provision setup for pivorag GCE instance
# This runs as the startup script on first boot

set -euo pipefail

PIVORAG_HOME="/opt/pivorag"
CHROMA_DATA="/opt/pivorag/chroma_data"

echo "=== PivoRAG GCE Setup Starting ==="

# System packages
apt-get update -y
apt-get install -y \
    python3.11 python3.11-venv python3.11-dev \
    python3-pip \
    git curl wget jq \
    build-essential

# Create pivorag user
useradd -r -m -s /bin/bash pivorag || true

# Create directories
mkdir -p "$PIVORAG_HOME" "$CHROMA_DATA"
chown -R pivorag:pivorag "$PIVORAG_HOME"

# Python venv
sudo -u pivorag python3.11 -m venv "$PIVORAG_HOME/venv"
sudo -u pivorag "$PIVORAG_HOME/venv/bin/pip" install --upgrade pip

# Install ChromaDB
sudo -u pivorag "$PIVORAG_HOME/venv/bin/pip" install chromadb

# ChromaDB systemd service
cat > /etc/systemd/system/chromadb.service << 'UNIT'
[Unit]
Description=ChromaDB Vector Database
After=network.target

[Service]
Type=simple
User=pivorag
WorkingDirectory=/opt/pivorag
ExecStart=/opt/pivorag/venv/bin/chroma run --host 0.0.0.0 --port 8000 --path /opt/pivorag/chroma_data
Restart=on-failure
RestartSec=5
Environment=ANONYMIZED_TELEMETRY=false

[Install]
WantedBy=multi-user.target
UNIT

systemctl daemon-reload
systemctl enable chromadb
systemctl start chromadb

# Fetch Neo4j credentials from Secret Manager
echo "=== Fetching Neo4j credentials ==="
NEO4J_CREDS=$(gcloud secrets versions access latest --secret=pivorag-neo4j-credentials 2>/dev/null || echo "{}")
echo "$NEO4J_CREDS" > "$PIVORAG_HOME/.neo4j-creds.json"
chmod 600 "$PIVORAG_HOME/.neo4j-creds.json"
chown pivorag:pivorag "$PIVORAG_HOME/.neo4j-creds.json"

echo "=== PivoRAG GCE Setup Complete ==="
echo "ChromaDB running on port 8000"
echo "Neo4j credentials stored at $PIVORAG_HOME/.neo4j-creds.json"
