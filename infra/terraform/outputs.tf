output "gce_instance_ip" {
  description = "External IP of the experiment GCE instance"
  value       = google_compute_instance.pivorag.network_interface[0].access_config[0].nat_ip
}

output "gce_instance_name" {
  description = "Name of the GCE instance"
  value       = google_compute_instance.pivorag.name
}

output "gcs_bucket_name" {
  description = "Name of the artifacts GCS bucket"
  value       = google_storage_bucket.artifacts.name
}

output "gcs_bucket_url" {
  description = "URL of the artifacts GCS bucket"
  value       = google_storage_bucket.artifacts.url
}

output "neo4j_secret_name" {
  description = "Secret Manager secret containing Neo4j credentials"
  value       = google_secret_manager_secret.neo4j_credentials.secret_id
}

output "ssh_command" {
  description = "SSH command to connect to the GCE instance"
  value       = "gcloud compute ssh ${google_compute_instance.pivorag.name} --zone ${var.zone} --project ${var.project_id}"
}
