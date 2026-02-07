resource "google_service_account" "pivorag" {
  account_id   = "pivorag-experiment"
  display_name = "PivoRAG Experiment Service Account"
  description  = "Service account for pivorag GCE instance"
}

# GCS access for data and results
resource "google_project_iam_member" "storage_admin" {
  project = var.project_id
  role    = "roles/storage.objectAdmin"
  member  = "serviceAccount:${google_service_account.pivorag.email}"
}

# Secret Manager access for Neo4j credentials
resource "google_project_iam_member" "secret_accessor" {
  project = var.project_id
  role    = "roles/secretmanager.secretAccessor"
  member  = "serviceAccount:${google_service_account.pivorag.email}"
}

# Logging for experiment audit trail
resource "google_project_iam_member" "log_writer" {
  project = var.project_id
  role    = "roles/logging.logWriter"
  member  = "serviceAccount:${google_service_account.pivorag.email}"
}
