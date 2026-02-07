variable "project_id" {
  description = "GCP project ID"
  type        = string
}

variable "region" {
  description = "GCP region"
  type        = string
  default     = "us-central1"
}

variable "zone" {
  description = "GCP zone"
  type        = string
  default     = "us-central1-a"
}

variable "environment" {
  description = "Environment name (dev, staging, prod)"
  type        = string
  default     = "dev"
}

variable "gce_machine_type" {
  description = "GCE instance machine type"
  type        = string
  default     = "e2-standard-4"
}

variable "gce_disk_size_gb" {
  description = "Boot disk size in GB"
  type        = number
  default     = 100
}

variable "neo4j_aura_uri" {
  description = "Neo4j AuraDB connection URI (provisioned externally)"
  type        = string
  sensitive   = true
}

variable "neo4j_aura_password" {
  description = "Neo4j AuraDB password"
  type        = string
  sensitive   = true
}

variable "allowed_ssh_cidrs" {
  description = "CIDR blocks allowed to SSH into GCE instance"
  type        = list(string)
  default     = []
}
