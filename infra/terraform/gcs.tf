resource "google_storage_bucket" "artifacts" {
  name          = "pivorag-artifacts-${var.project_id}"
  location      = var.region
  force_destroy = false

  uniform_bucket_level_access = true

  versioning {
    enabled = true
  }

  lifecycle_rule {
    action {
      type = "Delete"
    }
    condition {
      age = 90 # days — intermediate files
      matches_prefix = ["data/intermediate/"]
    }
  }

  labels = {
    project     = "pivorag"
    environment = var.environment
  }
}
