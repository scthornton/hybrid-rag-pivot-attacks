resource "google_compute_network" "pivorag" {
  name                    = "pivorag-network"
  auto_create_subnetworks = false
}

resource "google_compute_subnetwork" "pivorag" {
  name          = "pivorag-subnet"
  ip_cidr_range = "10.0.1.0/24"
  region        = var.region
  network       = google_compute_network.pivorag.id
}

resource "google_compute_firewall" "allow_ssh" {
  name    = "pivorag-allow-ssh"
  network = google_compute_network.pivorag.name

  allow {
    protocol = "tcp"
    ports    = ["22"]
  }

  source_ranges = length(var.allowed_ssh_cidrs) > 0 ? var.allowed_ssh_cidrs : ["0.0.0.0/0"]
  target_tags   = ["pivorag-instance"]
}

resource "google_compute_firewall" "allow_internal" {
  name    = "pivorag-allow-internal"
  network = google_compute_network.pivorag.name

  allow {
    protocol = "tcp"
    ports    = ["8000"]  # ChromaDB
  }

  allow {
    protocol = "icmp"
  }

  source_ranges = ["10.0.1.0/24"]
  target_tags   = ["pivorag-instance"]
}

# Allow outbound to Neo4j AuraDB (bolt+s on 7687)
resource "google_compute_firewall" "allow_neo4j_egress" {
  name      = "pivorag-allow-neo4j-egress"
  network   = google_compute_network.pivorag.name
  direction = "EGRESS"

  allow {
    protocol = "tcp"
    ports    = ["7687", "443"]
  }

  destination_ranges = ["0.0.0.0/0"]
  target_tags        = ["pivorag-instance"]
}
