terraform {
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 3.5"
    }
  }

  required_version = ">= 0.13"
}

provider "google" {
  credentials = file(var.GOOGLE_CREDENTIALS)
  project     = var.project_id
  region      = var.region
}



resource "google_compute_network" "vpc_network" {
  name                    = "my-custom-mode-network"
  auto_create_subnetworks = false
  mtu                     = 1460
}

resource "google_compute_subnetwork" "default" {
  name          = "my-custom-subnet"
  ip_cidr_range = "10.0.1.0/24"
  region        = "us-west1"
  network       = google_compute_network.vpc_network.id
}

resource "google_compute_instance" "default" {
  name         = "emailnotifier"
  machine_type = "f1-micro"
  zone         = "us-west1-a"
  tags         = ["ssh"]

  boot_disk {
    initialize_params {
      image = "debian-cloud/debian-11"
    }
  }

  metadata_startup_script = <<-EOF
  #! /bin/bash
  sudo apt-get update
  sudo apt-get install -yq build-essential python3-pip rsync

  echo "Flask==3.1.0
    authlib==1.4.0
    gunicorn==20.1.0
    psycopg2-binary==2.9.3
    requests
    google-cloud-monitoring
    google-cloud-logging
    sendgrid==6.9.1" > /tmp/requirements.txt

  # Install Python packages from requirements.txt
  pip3 install -r /tmp/requirements.txt
EOF

  network_interface {
    subnetwork = google_compute_subnetwork.default.id

    access_config {

    }
  }
}

resource "google_cloud_scheduler_job" "default" {
  name      = var.scheduler_job_name
  schedule  = "*/5 * * * *"
  time_zone = "UTC"

  http_target {
    uri        = "https://${var.app_engine_service_name}-dot-${var.project_id}.appspot.com/send"
    http_method = "GET"
  }
  
  retry_config {
    retry_count = 1
  }
}


output "app_engine_url" {
  value = "https://${var.app_engine_service_name}-dot-${var.project_id}.appspot.com/"
}
