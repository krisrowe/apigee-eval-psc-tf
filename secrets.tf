

# --- FAKE SECRET FOR DENY-DELETES TEST ---
# Uses DEFAULT provider (SA identity) - this is what the deny policy tests!
resource "google_secret_manager_secret" "fake_secret" {
  count     = var.fake_secret ? 1 : 0
  secret_id = "fake-secret"
  project   = var.gcp_project_id

  replication {
    auto {}
  }
  depends_on = [google_project_service.secretmanager]
}

resource "google_secret_manager_secret_version" "fake_secret_v1" {
  count       = var.fake_secret ? 1 : 0
  secret      = google_secret_manager_secret.fake_secret[0].id
  secret_data = "placeholder"
}
