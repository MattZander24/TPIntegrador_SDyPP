data "google_project" "project" {
  project_id = var.project_id
}

# ---- VPC nativa ----
resource "google_compute_network" "vpc" {
  name                    = "${var.cluster_name}-vpc"
  auto_create_subnetworks = false
}

resource "google_compute_subnetwork" "subnet" {
  name          = "${var.cluster_name}-subnet"
  network       = google_compute_network.vpc.id
  region        = var.region
  ip_cidr_range = "10.0.0.0/16"

  secondary_ip_range {
    range_name    = "pods"
    ip_cidr_range = "10.1.0.0/16"
  }

  secondary_ip_range {
    range_name    = "services"
    ip_cidr_range = "10.2.0.0/20"
  }

  private_ip_google_access = true
}

# ---- GKE cluster zonal ----
resource "google_container_cluster" "cluster" {
  provider = google-beta

  name     = var.cluster_name
  location = var.zone

  network    = google_compute_network.vpc.id
  subnetwork = google_compute_subnetwork.subnet.id

  # VPC-native (alias IP)
  ip_allocation_policy {
    cluster_secondary_range_name  = "pods"
    services_secondary_range_name = "services"
  }

  # Eliminar nodo por defecto
  remove_default_node_pool = true
  initial_node_count       = 1

  # Workload Identity
  workload_identity_config {
    workload_pool = "${var.project_id}.svc.id.goog"
  }

  # Private cluster (nodos sin IP pública)
  # Cluster zonal con nodos públicos (más barato, sin NAT)
  master_authorized_networks_config {
    cidr_blocks {
      cidr_block   = "0.0.0.0/0"
      display_name = "all"
    }
  }

  # Release channel
  release_channel {
    channel = "REGULAR"
  }

  # Addons
  addons_config {
    http_load_balancing {
      disabled = false
    }
    horizontal_pod_autoscaling {
      disabled = false
    }
    network_policy_config {
      disabled = true
    }
  }

  deletion_protection = false
}

# ---- Node Pool: Infraestructura (Redis, RabbitMQ) ----
resource "google_container_node_pool" "infra" {
  name     = "infra"
  location = var.zone
  cluster  = google_container_cluster.cluster.name

  initial_node_count = var.infra_min_nodes

  autoscaling {
    min_node_count = var.infra_min_nodes
    max_node_count = var.infra_max_nodes
  }

  management {
    auto_repair  = true
    auto_upgrade = true
  }

  node_config {
    machine_type = var.infra_machine_type
    disk_size_gb = 20
    disk_type    = "pd-standard"
    image_type   = "COS_CONTAINERD"

    service_account = google_service_account.nodes.email
    oauth_scopes = [
      "https://www.googleapis.com/auth/cloud-platform",
    ]

    labels = {
      pool = "infra"
    }

    tags = ["infra"]

    # Taint para que solo corran servicios de infra
    taint {
      key    = "pool"
      value  = "infra"
      effect = "NO_SCHEDULE"
    }
  }
}

# ---- Node Pool: Aplicaciones (NCT, TrP, API, Frontend) ----
resource "google_container_node_pool" "apps" {
  name     = "apps"
  location = var.zone
  cluster  = google_container_cluster.cluster.name

  initial_node_count = var.apps_min_nodes

  autoscaling {
    min_node_count = var.apps_min_nodes
    max_node_count = var.apps_max_nodes
  }

  management {
    auto_repair  = true
    auto_upgrade = true
  }

  node_config {
    machine_type = var.apps_machine_type
    disk_size_gb = 50
    disk_type    = "pd-standard"
    image_type   = "COS_CONTAINERD"

    service_account = google_service_account.nodes.email
    oauth_scopes = [
      "https://www.googleapis.com/auth/cloud-platform",
    ]

    labels = {
      pool = "apps"
    }

    tags = ["apps"]
  }
}

# ---- Service Account para nodos GKE ----
resource "google_service_account" "nodes" {
  account_id   = "${var.cluster_name}-nodes"
  display_name = "GKE Node SA - ${var.cluster_name}"
}

# ---- Workload Identity: IAM bindings ----
resource "google_service_account" "external_secrets" {
  account_id   = "external-secrets-sa"
  display_name = "External Secrets Operator SA"
}

resource "google_project_iam_member" "external_secrets_sm" {
  project = var.project_id
  role    = "roles/secretmanager.secretAccessor"
  member  = "serviceAccount:${google_service_account.external_secrets.email}"
}

resource "google_service_account_iam_member" "external_secrets_wif" {
  service_account_id = google_service_account.external_secrets.name
  role               = "roles/iam.workloadIdentityUser"
  member             = format("serviceAccount:%s.svc.id.goog[external-secrets/external-secrets]",
    var.project_id
  )
  depends_on = [google_container_cluster.cluster]
}

# ---- Secret Manager: RabbitMQ credenciales y TLS ----
# ---- Artifact Registry ----
resource "google_artifact_registry_repository" "images" {
  location      = var.region
  repository_id = "voxchain-images"
  format        = "DOCKER"
}

# ---- Providers ----
provider "google" {
  project = var.project_id
  region  = var.region
}

provider "google-beta" {
  project = var.project_id
  region  = var.region
}

data "google_client_config" "default" {}

provider "kubernetes" {
  host                   = "https://${google_container_cluster.cluster.endpoint}"
  token                  = data.google_client_config.default.access_token
  cluster_ca_certificate = base64decode(
    google_container_cluster.cluster.master_auth[0].cluster_ca_certificate
  )
}

provider "helm" {
  kubernetes {
    host                   = "https://${google_container_cluster.cluster.endpoint}"
    token                  = data.google_client_config.default.access_token
    cluster_ca_certificate = base64decode(
      google_container_cluster.cluster.master_auth[0].cluster_ca_certificate
    )
  }
}

# ---- CI/CD: Workload Identity Federation (GitHub Actions) ----
resource "google_iam_workload_identity_pool" "github" {
  workload_identity_pool_id = "github-actions"
  display_name              = "GitHub Actions Pool"
}

resource "google_iam_workload_identity_pool_provider" "github" {
  workload_identity_pool_id          = google_iam_workload_identity_pool.github.workload_identity_pool_id
  workload_identity_pool_provider_id = "github-provider"
  display_name                       = "GitHub Actions Provider"
  attribute_mapping = {
    "google.subject"       = "assertion.sub"
    "attribute.actor"      = "assertion.actor"
    "attribute.repository" = "assertion.repository"
  }
  attribute_condition = "assertion.repository == '${var.github_repository}'"
  oidc {
    issuer_uri = "https://token.actions.githubusercontent.com"
  }
}

resource "google_service_account" "cicd" {
  account_id   = "${var.cluster_name}-cicd"
  display_name = "CI/CD Service Account"
}

resource "google_project_iam_member" "cicd_container_admin" {
  project = var.project_id
  role    = "roles/container.developer"
  member  = "serviceAccount:${google_service_account.cicd.email}"
}

resource "google_project_iam_member" "cicd_artifact_writer" {
  project = var.project_id
  role    = "roles/artifactregistry.writer"
  member  = "serviceAccount:${google_service_account.cicd.email}"
}

resource "google_project_iam_member" "nodes_artifact_reader" {
  project = var.project_id
  role    = "roles/artifactregistry.reader"
  member  = "serviceAccount:${google_service_account.nodes.email}"
}

resource "google_service_account_iam_member" "cicd_wif" {
  service_account_id = google_service_account.cicd.name
  role               = "roles/iam.workloadIdentityUser"
  member = format("principalSet://iam.googleapis.com/%s/attribute.repository/%s",
    google_iam_workload_identity_pool.github.name,
    var.github_repository
  )
}

# ---- External Secrets Operator (via Helm) ----
resource "helm_release" "external_secrets" {
  name       = "external-secrets"
  repository = "https://charts.external-secrets.io"
  chart      = "external-secrets"
  version    = "0.10.0"
  namespace  = "external-secrets"
  create_namespace = true

  set {
    name  = "serviceAccount.create"
    value = "true"
  }
  set {
    name  = "serviceAccount.name"
    value = "external-secrets"
  }
  set {
    name  = "serviceAccount.annotations.iam\\.gke\\.io/gcp-service-account"
    value = google_service_account.external_secrets.email
  }

  depends_on = [google_container_cluster.cluster]
}

# ---- kube-prometheus-stack (Prometheus + Grafana + Alertmanager) ----
resource "helm_release" "kube_prometheus_stack" {
  name       = "kube-prometheus-stack"
  repository = "https://prometheus-community.github.io/helm-charts"
  chart      = "kube-prometheus-stack"
  version    = "61.0.0"
  namespace  = "monitoring"
  create_namespace = true

  values = [yamlencode({
    grafana = {
      adminPassword = var.grafana_admin_password
      ingress = {
        enabled = false
      }
      extraEnvVars = {
        GF_SERVER_ROOT_URL = "https://grafana.voxchain.34.95.143.13.sslip.io"
      }
      persistence = {
        enabled = true
        size = "10Gi"
      }
    }
    prometheus = {
      prometheusSpec = {
        serviceMonitorSelectorNilUsesHelmValues = false
        serviceMonitorSelector = {}
        retention = "7d"
        resources = {
          requests = {
            cpu = "500m"
            memory = "2Gi"
          }
        }
      }
    }
  })]

  depends_on = [google_container_cluster.cluster]
}

# ---- nginx-ingress controller (reemplaza GCE Ingress) ----
resource "helm_release" "ingress_nginx" {
  name       = "ingress-nginx"
  repository = "https://kubernetes.github.io/ingress-nginx"
  chart      = "ingress-nginx"
  version    = "4.11.0"
  namespace  = "ingress-nginx"
  create_namespace = true

  set {
    name  = "controller.service.type"
    value = "LoadBalancer"
  }

  depends_on = [google_container_cluster.cluster]
}

# ---- cert-manager (Let's Encrypt) ----
resource "helm_release" "cert_manager" {
  name       = "cert-manager"
  repository = "https://charts.jetstack.io"
  chart      = "cert-manager"
  version    = "v1.16.0"
  namespace  = "cert-manager"
  create_namespace = true

  set {
    name  = "installCRDs"
    value = "true"
  }

  depends_on = [google_container_cluster.cluster]
}
