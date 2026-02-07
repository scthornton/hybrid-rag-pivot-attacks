resource "google_compute_instance" "pivorag" {
  name         = "pivorag-experiment-${var.environment}"
  machine_type = var.gce_machine_type
  zone         = var.zone
  tags         = ["pivorag-instance"]

  boot_disk {
    initialize_params {
      image = "ubuntu-os-cloud/ubuntu-2204-lts"
      size  = var.gce_disk_size_gb
      type  = "pd-ssd"
    }
  }

  network_interface {
    subnetwork = google_compute_subnetwork.pivorag.id

    access_config {
      # Ephemeral external IP
    }
  }

  service_account {
    email  = google_service_account.pivorag.email
    scopes = ["cloud-platform"]
  }

  metadata_startup_script = file("${path.module}/../scripts/setup_gce.sh")

  metadata = {
    enable-oslogin = "TRUE"
  }

  labels = {
    project     = "pivorag"
    environment = var.environment
  }
}
