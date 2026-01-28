# Apigee Eval Org with PSC Terraform

This repository provides a reusable Terraform script to provision a complete Apigee evaluation organization in Google Cloud.

The primary goal is to create a modern, secure Apigee setup that avoids VPC peering, instead relying entirely on **Private Service Connect (PSC)** for all traffic.

## Key Features

- **No VPC Peering:** Simplifies network architecture and reduces dependencies.
- **Northbound PSC:** Exposes the Apigee runtime via an External HTTPS Load Balancer using a PSC Network Endpoint Group (NEG).
- **Custom Domain:** Supports custom domain names for the API ingress endpoint with a managed SSL certificate.
- **Southbound PSC (Example):** Includes a sample API proxy (`weather-api`) that demonstrates how to securely connect to a backend microservice via PSC. *(Note: The backend service and its corresponding PSC setup are not included in this script and must be provisioned separately).*
- **Automated Setup:** A simple shell script helps configure the GCP project ID.

## Prerequisites

-   A Google Cloud Project with billing enabled.
-   The `gcloud` CLI installed and authenticated (`gcloud auth application-default login`).
-   Terraform installed (version >= 1.4).
-   A registered domain name that you can control to point to the Load Balancer's IP address.

## Quick Start

1.  **Clone the Repository**
    ```bash
    git clone <repository-url>
    cd apigee-eval-psc-tf
    ```

2.  **Prepare Configuration**

    You have two options: the automated script (recommended) or manual setup.

    **Option A: Automated Script**
    Run the configuration script. It will prompt you for your GCP Project ID and automatically create your `terraform.tfvars` file.

    ```bash
    bash scripts/configure_project.sh
    ```

    **Option B: Manual Setup**
    Copy the example variables file.

    ```bash
    cp terraform.tfvars.example terraform.tfvars
    ```
    Now, edit `terraform.tfvars` and set the required values for `gcp_project_id` and `domain_name`.

3.  **Deploy with Terraform**

    Initialize Terraform to download the necessary providers.
    ```bash
    terraform init
    ```

    Preview the changes that will be made.
    ```bash
    terraform plan
    ```

    Apply the configuration to create the Apigee resources. This step can take a significant amount of time (often 45-60 minutes) for the Apigee organization and instance to be provisioned.
    ```bash
    terraform apply
    ```

## Backup and Recovery

This Terraform project is designed to be reusable. To recreate or manage this environment from another machine, you only need a few key pieces of information.

-   **`terraform.tfvars`:** This is the most critical file to back up manually. It contains the specific variables for your deployment, such as your project ID and domain name.
-   **Terraform State File (`terraform.tfstate`):** Terraform uses this file to keep track of the resources it manages.
    -   By default, this file is created locally. You should back this file up if you want to manage the infrastructure from a different location.
    -   **Recommendation:** For any serious or collaborative use, it is highly recommended to configure a [Terraform remote backend](https://www.terraform.io/language/state/backends) (like a Google Cloud Storage bucket). This stores the state file securely and centrally, making it accessible to you or your team from anywhere. The `.gitignore` file is already configured to ignore local state files.

By backing up `terraform.tfvars` and your state file, you can clone this repository on any machine, restore those files, and continue managing your Apigee environment seamlessly.