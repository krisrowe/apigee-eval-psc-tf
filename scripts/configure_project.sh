#!/bin/bash

set -e

LABEL_KEY="apigee-eval-psc-tf"
LABEL_VALUE="default"
TFVARS_FILE="terraform.tfvars"
PROJECT_ID=""
OVERRIDE_PROJECT_ID=""

# Parse command-line arguments
while [[ $# -gt 0 ]]; do
  key="$1"
  case $key in
    --project)
      OVERRIDE_PROJECT_ID="$2"
      shift # past argument
      shift # past value
      ;;
    *)
      # unknown option
      shift # past argument
      ;;
  esac
done

# 1. Check for override project ID from command line
if [[ -n "$OVERRIDE_PROJECT_ID" ]]; then
  PROJECT_ID="$OVERRIDE_PROJECT_ID"
  echo "Using project ID from command line: '$PROJECT_ID'."
  # Label the project if it's new/overridden
  echo "Labeling project '$PROJECT_ID' with '$LABEL_KEY=$LABEL_VALUE'..."
  gcloud projects add-labels "$PROJECT_ID" --labels="$LABEL_KEY=$LABEL_VALUE" || echo "Warning: Could not add label to project '$PROJECT_ID'. It might not exist or you lack permissions."
else
  # 2. Check if gcp_project_id is already in terraform.tfvars
  if [ -f "$TFVARS_FILE" ]; then
    # Extract value, removing quotes and whitespace
    EXISTING_PROJECT_ID=$(grep "gcp_project_id" "$TFVARS_FILE" | awk -F'=' '{print $2}' | tr -d ' "' | xargs)
    if [[ -n "$EXISTING_PROJECT_ID" ]]; then
      PROJECT_ID="$EXISTING_PROJECT_ID"
      echo "Project already configured in $TFVARS_FILE: '$PROJECT_ID'. No alternate project specified."
      echo "Configuration complete."
      exit 0
    fi
  fi

  # 3. Look for a project with the specified label
  FOUND_PROJECT_ID=$(gcloud projects list --filter="labels.$LABEL_KEY=$LABEL_VALUE" --format="value(projectId)" --limit=1)

  if [[ -n "$FOUND_PROJECT_ID" ]]; then
    PROJECT_ID="$FOUND_PROJECT_ID"
    echo "Found project '$PROJECT_ID' with the label '$LABEL_KEY=$LABEL_VALUE'."
  else
    echo "No project found with the label '$LABEL_KEY=$LABEL_VALUE'."
    read -p "Please enter the GCP Project ID to use: " USER_INPUT_PROJECT_ID

    if [[ -z "$USER_INPUT_PROJECT_ID" ]]; then
      echo "Project ID cannot be empty."
      exit 1
    fi
    PROJECT_ID="$USER_INPUT_PROJECT_ID"

    echo "Labeling project '$PROJECT_ID' with '$LABEL_KEY=$LABEL_VALUE'..."
    gcloud projects add-labels "$PROJECT_ID" --labels="$LABEL_KEY=$LABEL_VALUE"
  fi
fi

# 4. Write/update gcp_project_id in terraform.tfvars
echo "Setting gcp_project_id in $TFVARS_FILE..."
echo "gcp_project_id = \"$PROJECT_ID\"" > "$TFVARS_FILE"

echo "Configuration complete. The GCP Project ID is set to '$PROJECT_ID' in $TFVARS_FILE."
echo "You can now run 'terraform plan' or 'terraform apply' directly."