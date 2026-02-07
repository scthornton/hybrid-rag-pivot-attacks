#!/bin/bash
# Clean shutdown and optional data export before destroying infrastructure
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TERRAFORM_DIR="$SCRIPT_DIR/../terraform"

echo "=== PivoRAG Teardown ==="

# Check if terraform state exists
if [ ! -f "$TERRAFORM_DIR/terraform.tfstate" ] && [ ! -d "$TERRAFORM_DIR/.terraform" ]; then
    echo "No Terraform state found. Nothing to tear down."
    exit 0
fi

cd "$TERRAFORM_DIR"

# Get instance and bucket info
INSTANCE_NAME=$(terraform output -raw gce_instance_name 2>/dev/null || echo "")
BUCKET_NAME=$(terraform output -raw gcs_bucket_name 2>/dev/null || echo "")
PROJECT_ID=$(terraform output -raw project_id 2>/dev/null || echo "")

if [ -n "$INSTANCE_NAME" ] && [ -n "$BUCKET_NAME" ]; then
    echo "Exporting experiment data to GCS before teardown..."
    gcloud compute ssh "$INSTANCE_NAME" --command \
        "sudo tar czf /tmp/pivorag-export.tar.gz /opt/pivorag/chroma_data 2>/dev/null || true" \
        2>/dev/null || true

    gcloud compute scp "$INSTANCE_NAME:/tmp/pivorag-export.tar.gz" \
        "/tmp/pivorag-export-$(date +%Y%m%d).tar.gz" \
        2>/dev/null || true
fi

echo ""
echo "WARNING: This will destroy all GCP resources created by Terraform."
echo "Data in GCS bucket will NOT be deleted (force_destroy=false)."
echo ""
read -p "Proceed with teardown? (yes/no): " confirm

if [ "$confirm" = "yes" ]; then
    terraform destroy -auto-approve
    echo "=== Teardown complete ==="
else
    echo "Teardown cancelled."
fi
