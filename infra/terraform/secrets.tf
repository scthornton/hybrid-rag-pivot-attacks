# Secret Manager entries for LLM API keys (generation evaluation)

resource "google_secret_manager_secret" "openai_key" {
  count     = var.openai_api_key != "" ? 1 : 0
  secret_id = "pivorag-openai-api-key"

  replication {
    auto {}
  }

  labels = {
    project     = "pivorag"
    environment = var.environment
  }
}

resource "google_secret_manager_secret_version" "openai_key" {
  count       = var.openai_api_key != "" ? 1 : 0
  secret      = google_secret_manager_secret.openai_key[0].id
  secret_data = var.openai_api_key
}

resource "google_secret_manager_secret" "anthropic_key" {
  count     = var.anthropic_api_key != "" ? 1 : 0
  secret_id = "pivorag-anthropic-api-key"

  replication {
    auto {}
  }

  labels = {
    project     = "pivorag"
    environment = var.environment
  }
}

resource "google_secret_manager_secret_version" "anthropic_key" {
  count       = var.anthropic_api_key != "" ? 1 : 0
  secret      = google_secret_manager_secret.anthropic_key[0].id
  secret_data = var.anthropic_api_key
}

resource "google_secret_manager_secret" "deepseek_key" {
  count     = var.deepseek_api_key != "" ? 1 : 0
  secret_id = "pivorag-deepseek-api-key"

  replication {
    auto {}
  }

  labels = {
    project     = "pivorag"
    environment = var.environment
  }
}

resource "google_secret_manager_secret_version" "deepseek_key" {
  count       = var.deepseek_api_key != "" ? 1 : 0
  secret      = google_secret_manager_secret.deepseek_key[0].id
  secret_data = var.deepseek_api_key
}
