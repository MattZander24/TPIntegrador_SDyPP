variable "project_id" {
  description = "GCP Project ID"
  type        = string
  default     = "voxchain"
}

variable "region" {
  description = "GCP region"
  type        = string
  default     = "southamerica-east1"
}

variable "zone" {
  description = "GCP zone for zonal cluster"
  type        = string
  default     = "southamerica-east1-a"
}

variable "cluster_name" {
  description = "GKE cluster name"
  type        = string
  default     = "voxchain"
}

variable "infra_machine_type" {
  description = "Machine type for infrastructure node pool"
  type        = string
  default     = "e2-small"
}

variable "infra_min_nodes" {
  description = "Minimum nodes in infra pool"
  type        = number
  default     = 1
}

variable "infra_max_nodes" {
  description = "Maximum nodes in infra pool"
  type        = number
  default     = 2
}

variable "apps_machine_type" {
  description = "Machine type for applications node pool"
  type        = string
  default     = "e2-standard-2"
}

variable "apps_min_nodes" {
  description = "Minimum nodes in apps pool"
  type        = number
  default     = 2
}

variable "apps_max_nodes" {
  description = "Maximum nodes in apps pool"
  type        = number
  default     = 3
}

variable "github_repository" {
  description = "GitHub repository for CI/CD (formato: owner/repo)"
  type        = string
  default     = "MattZander24/TPIntegrador_SDyPP"
}
