# Developing API Proxies

This guide outlines the conventions and tools used for developing and validating API Proxies and Shared Flows within an environment managed by `apigee-tf`.

## Directory Structure

When developing proxies or shared flows, you should place them within the **Apigee Deployment Workspace (ADW)**—the local directory containing your `terraform.tfvars` configuration. This ensures that your development artifacts are properly isolated and tracked alongside the Terraform state for that specific Apigee Organization.

**Convention:**
*   **Proxies:** Place API proxy bundles in `<adw-dir>/apiproxies/<proxy-name>/apiproxy/`
*   **Shared Flows:** Place Shared Flow bundles in `<adw-dir>/sharedflows/<shared-flow-name>/sharedflowbundle/`

**Example Layout:**
```text
my-apigee-adw/
├── terraform.tfvars
├── apiproxies/
│   └── weather-api/
│       └── apiproxy/          # <-- The actual proxy bundle
│           ├── weather-api.xml
│           ├── proxies/
│           ├── targets/
│           └── policies/
└── sharedflows/
    └── security-common/
        └── sharedflowbundle/  # <-- The actual shared flow bundle
            ├── security-common.xml
            ├── sharedflows/
            └── policies/
```

## Validation Tools

It is highly recommended to validate your XML bundles *before* attempting to deploy them. The Apigee Management API will reject bundles with structural errors, but static analysis tools can catch these errors locally, saving significant debugging time.

### `apigeelint`

The primary tool for this is [apigeelint](https://github.com/apigee/apigeelint), a static code analysis tool maintained by Apigee.

#### Installation

`apigeelint` requires Node.js (version 20+) and npm (version 10.5.0+).

Install it globally via npm:

```bash
npm install -g apigeelint
```

#### Usage

Run `apigeelint` against your local proxy or shared flow directory. It will analyze your XML files for best practices, naming conventions, and structural integrity (e.g., ensuring a proxy has a `ProxyEndpoint`).

**To validate an API Proxy:**
```bash
apigeelint -s <adw-dir>/apiproxies/<proxy-name>/apiproxy -f table.js
```

**To validate a Shared Flow:**
```bash
apigeelint -s <adw-dir>/sharedflows/<shared-flow-name>/sharedflowbundle -f table.js
```

The `-f table.js` flag formats the output into an easy-to-read table. If there are structural errors (like a missing `proxies/default.xml` file), `apigeelint` will catch them before you deploy.