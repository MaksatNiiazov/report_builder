#!/usr/bin/env bash
set -euo pipefail

: "${TOKEN:?Set TOKEN to an Identity access token with service, role, and user management permissions}"

IDENTITY_URL="${IDENTITY_URL:-http://localhost:8500/api/v1}"
REPORT_BUILDER_URL="${REPORT_BUILDER_URL:-http://localhost:7505}"

curl --fail-with-body --silent --show-error \
  -X POST "${IDENTITY_URL}/services/connect" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d @- <<JSON
{
  "code": "report_builder",
  "name": "Report Builder",
  "description": "Safe parameterized reports from read-only database sources",
  "base_url": "${REPORT_BUILDER_URL}",
  "permissions": [
    {"code": "report_builder.reports.read", "name": "Read published reports"},
    {"code": "report_builder.reports.execute", "name": "Execute and export published reports"},
    {"code": "report_builder.reports.manage", "name": "Create and publish reports"},
    {"code": "report_builder.sources.manage", "name": "Manage read-only report data sources"},
    {"code": "report_builder.audit.read", "name": "Read report execution audit log"}
  ],
  "roles": [
    {
      "code": "report_builder_user",
      "name": "Report Builder User",
      "permission_codes": [
        "report_builder.reports.read",
        "report_builder.reports.execute"
      ]
    },
    {
      "code": "report_builder_admin",
      "name": "Report Builder Admin",
      "permission_codes": [
        "report_builder.reports.read",
        "report_builder.reports.execute",
        "report_builder.reports.manage",
        "report_builder.sources.manage",
        "report_builder.audit.read"
      ]
    }
  ]
}
JSON

