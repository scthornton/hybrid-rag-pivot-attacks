# Neo4j AuraDB is provisioned externally via the Neo4j Aura console.
# This file manages the credentials in GCP Secret Manager and
# any firewall/networking needed for connectivity.

resource "google_secret_manager_secret" "neo4j_credentials" {
  secret_id = "pivorag-neo4j-credentials"

  replication {
    auto {}
  }

  labels = {
    project     = "pivorag"
    environment = var.environment
  }
}

resource "google_secret_manager_secret_version" "neo4j_credentials" {
  secret = google_secret_manager_secret.neo4j_credentials.id

  secret_data = jsonencode({
    uri      = var.neo4j_aura_uri
    username = "neo4j"
    password = var.neo4j_aura_password
  })
}

# Grant the GCE service account access to read Neo4j secrets
resource "google_secret_manager_secret_iam_member" "neo4j_accessor" {
  secret_id = google_secret_manager_secret.neo4j_credentials.secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.pivorag.email}"
}
