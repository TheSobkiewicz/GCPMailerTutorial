
variable "region" {
  description = "The GCP region to deploy resources to."
  default     = "us-central1"
}

variable "GOOGLE_CREDENTIALS" {
  description = "Path to JSON credentials file for your service account."
  type        = string
  default = "credentials.json"
}


variable "app_engine_service_name" {
  description = "Name for the App Engine service."
  default     = "emailnotifier4"
}

variable "project_id" {
    default ="emailnotifier-448200"
}

variable "scheduler_job_name" {
    default ="send-emails"
}