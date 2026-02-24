# Risk Assessment Report

## 🎯 Risk Summary

**Risk Score**: 28/100
**Risk Level**: LOW
**Verdict**: ✅ Low risk - Safe to proceed

*Schema Version*: risk_report.v1
*Risk Model*: 0.2

## 📋 Resource Information

- **Resource ID**: `/subscriptions/6b085460-5f21-477e-ba44-1035046e9101/resourceGroups/azclis-copilot-rg-beta/providers/Microsoft.Dashboard/grafana/azcli-grafana-beta`
- **Type**: Service
- **Environment**: prod
- **Operations**: None

## ⚠️ Risk Factors

| Factor | Status | Points | Impact |
|--------|--------|--------|--------|
| 🟢 SafeFly-caused outages (180d) | miss | 0/15 | None |
| 🟢 Similar past incidents | miss | 0/12 | None |
| 🔴 Blast radius (subscriptions) | hit | 2/12 | Low |
| 🔴 Recent outages (180d) | hit | 5/10 | Medium |
| 🔴 Slow incident mitigation | hit | 10/10 | High |
| 🟢 Deployment frequency (30d) | miss | 0/10 | None |
| ⚪ Destructive operations | na | 0/10 | None |
| 🔴 High-severity incidents (Sev1/2, 180d) | hit | 3/8 | Low |
| 🔴 Resources in same ResourceGroup | hit | 8/8 | High |
| 🟢 Recent active outages (7d) | miss | 0/5 | None |

### Factor Details

**🟢 deployment.change_caused_outages: SafeFly-caused outages (180d)**

- **Status**: miss
- **Points**: 0 / 15
- **Reason**: Sev1/2 outages caused by SafeFly deployments indicate high deployment risk.

Evidence:
```json
{
  "safefly_caused_outages_180d": 0
}
```

**🟢 incident.recurrence: Similar past incidents**

- **Status**: miss
- **Points**: 0 / 12
- **Reason**: Recurring incidents suggest systematic issues.

Evidence:
```json
{
  "related_incidents": 0
}
```

**🔴 blast_radius.subscriptions: Blast radius (subscriptions)**

- **Status**: hit
- **Points**: 2 / 12
- **Reason**: More subscriptions under a service increases the blast radius.

Evidence:
```json
{
  "subscription_count": 1
}
```

**🔴 history.outages_180d: Recent outages (180d)**

- **Status**: hit
- **Points**: 5 / 10
- **Reason**: Recent outages suggest fragility and elevated change risk.

Evidence:
```json
{
  "historical_outages_180d": 1
}
```

**🔴 incident.mttm: Slow incident mitigation**

- **Status**: hit
- **Points**: 10 / 10
- **Reason**: Slow mitigation suggests recovery challenges.

Evidence:
```json
{
  "avg_mttm_minutes": 21617
}
```

**🟢 ops.deployments_30d: Deployment frequency (30d)**

- **Status**: miss
- **Points**: 0 / 10
- **Reason**: Higher deployment cadence increases concurrent-change risk.

Evidence:
```json
{
  "deployment_count_30d": 0
}
```

**⚪ change.destructive: Destructive operations**

- **Status**: na
- **Points**: 0 / 10
- **Reason**: No change operations provided.

Evidence:
```json
{
  "operations": []
}
```

**🔴 incident.severity_mix: High-severity incidents (Sev1/2, 180d)**

- **Status**: hit
- **Points**: 3 / 8
- **Reason**: High-severity incidents indicate service fragility.

Evidence:
```json
{
  "sev12_incident_count": 1
}
```

**🔴 resource.peer_impact: Resources in same ResourceGroup**

- **Status**: hit
- **Points**: 8 / 8
- **Reason**: More peer resources increase blast radius.

Evidence:
```json
{
  "peer_resource_count": 47
}
```

**🟢 ops.recent_active_outages: Recent active outages (7d)**

- **Status**: miss
- **Points**: 0 / 5
- **Reason**: Active outage incidents increase operational risk during changes.

Evidence:
```json
{
  "recent_active_outages": 0
}
```

## 💡 Recommendations

- This change appears safe to proceed
- Follow standard deployment procedures
- Multiple services affected - Coordinate with service owners
- Recent outages detected - Review incident history

## 📊 Supporting Evidence

```json
{
  "avg_mttm_minutes": 21617,
  "deployment_count_30d": 0,
  "historical_outages_180d": 1,
  "peer_resource_count": 47,
  "recent_active_outages": 0,
  "related_incidents": 0,
  "repo_count": 50,
  "resource_id": "/subscriptions/6b085460-5f21-477e-ba44-1035046e9101/resourceGroups/azclis-copilot-rg-beta/providers/Microsoft.Dashboard/grafana/azcli-grafana-beta",
  "safefly_caused_outages_180d": 0,
  "service_name": "Azure CLI Tools - Azure CLI, PowerShell and Terraform",
  "service_subscriptions": [
    {
      "environment": "NonProd",
      "status": 1,
      "subscription_id": "0576f15f-eb64-41d3-99a2-e28f38ccd53c",
      "subscription_name": "Azure Verified Module Terraform"
    },
    {
      "environment": "Prod",
      "status": 1,
      "subscription_id": "732d0b2b-89f0-42b4-b652-53f7253afaab",
      "subscription_name": "Azure Management Experience Infra"
    },
    {
      "environment": "NonProd",
      "status": 1,
      "subscription_id": "85b3dbca-5974-4067-9669-67a141095a76",
      "subscription_name": "Terraform Testing on Azure with TTL = 2 Days"
    },
    {
      "environment": "NonProd",
      "status": 1,
      "subscription_id": "9e223dbe-3399-4e19-88eb-0975f02ac87f",
      "subscription_name": "Azure SDK Powershell Test - Manual"
    },
    {
      "environment": "NonProd",
      "status": 1,
      "subscription_id": "f64d4ee8-be94-457d-ba26-3fa6b6506cef",
      "subscription_name": "OSS Integration DevINT with TTL = 7 Days"
    },
    {
      "environment": "NonProd",
      "status": 1,
      "subscription_id": "0b1f6471-1bf0-4dda-aec3-cb9272f09590",
      "subscription_name": "AzureSDKTest"
    },
    {
      "environment": "NonProd",
      "status": 1,
      "subscription_id": "1c638cf4-608f-4ee6-b680-c329e824c3a8",
      "subscription_name": "Azure CLI Tests with TTL = 2 Days"
    },
    {
      "environment": "NonProd",
      "status": 1,
      "subscription_id": "6b085460-5f21-477e-ba44-1035046e9101",
      "subscription_name": "Azure SDK Infrastructure"
    },
    {
      "environment": "NonProd",
      "status": 1,
      "subscription_id": "23a32706-03c1-4920-a6ac-1b7c8de24bb4",
      "subscription_name": "Azure SDK Mooncake sandbox"
    }
  ],
  "service_tree_id": "092c677a-6386-4fa8-a485-991d3f9aa010",
  "sev12_incident_count": 1,
  "source_repos": [
    {
      "repo_url": "https://github.com/Azure/azure-cli-pr",
      "service_id": "092c677a-6386-4fa8-a485-991d3f9aa010",
      "service_name": "Azure CLI Tools - Azure CLI, PowerShell and Terraform",
      "source_code_type": "GitHub"
    },
    {
      "repo_url": "https://github.com/Azure/terraform-azure-azureacademy-avd-lab",
      "service_id": "092c677a-6386-4fa8-a485-991d3f9aa010",
      "service_name": "Azure CLI Tools - Azure CLI, PowerShell and Terraform",
      "source_code_type": "GitHub"
    },
    {
      "repo_url": "https://github.com/microsoft/msgraph-vscode",
      "service_id": "092c677a-6386-4fa8-a485-991d3f9aa010",
      "service_name": "Azure CLI Tools - Azure CLI, PowerShell and Terraform",
      "source_code_type": "GitHub"
    },
    {
      "repo_url": "https://dev.azure.com/azclitools/release/_git/vscode-azureterraform-release",
      "service_id": "092c677a-6386-4fa8-a485-991d3f9aa010",
      "service_name": "Azure CLI Tools - Azure CLI, PowerShell and Terraform",
      "source_code_type": "Azure DevOps Git"
    },
    {
      "repo_url": "https://dev.azure.com/azclitools/internal/_git/test-cli-upload",
      "service_id": "092c677a-6386-4fa8-a485-991d3f9aa010",
      "service_name": "Azure CLI Tools - Azure CLI, PowerShell and Terraform",
      "source_code_type": "Azure DevOps Git"
    },
    {
      "repo_url": "https://github.com/Azure/azure-sdk-tools-samples",
      "service_id": "092c677a-6386-4fa8-a485-991d3f9aa010",
      "service_name": "Azure CLI Tools - Azure CLI, PowerShell and Terraform",
      "source_code_type": "GitHub"
    },
    {
      "repo_url": "https://github.com/Azure/autorest.cli",
      "service_id": "092c677a-6386-4fa8-a485-991d3f9aa010",
      "service_name": "Azure CLI Tools - Azure CLI, PowerShell and Terraform",
      "source_code_type": "GitHub"
    },
    {
      "repo_url": "https://dev.azure.com/azclitools/internal/_git/py-microsoft-security-utilities",
      "service_id": "092c677a-6386-4fa8-a485-991d3f9aa010",
      "service_name": "Azure CLI Tools - Azure CLI, PowerShell and Terraform",
      "source_code_type": "Azure DevOps Git"
    },
    {
      "repo_url": "https://dev.azure.com/azclitools/internal/_git/tf-appservice-featuretest",
      "service_id": "092c677a-6386-4fa8-a485-991d3f9aa010",
      "service_name": "Azure CLI Tools - Azure CLI, PowerShell and Terraform",
      "source_code_type": "Azure DevOps Git"
    },
    {
      "repo_url": "https://github.com/Azure/terraform-azurerm-avm-ptn-aks-production",
      "service_id": "092c677a-6386-4fa8-a485-991d3f9aa010",
      "service_name": "Azure CLI Tools - Azure CLI, PowerShell and Terraform",
      "source_code_type": "GitHub"
    },
    {
      "repo_url": "https://github.com/Azure/terraform-provider-modtm",
      "service_id": "092c677a-6386-4fa8-a485-991d3f9aa010",
      "service_name": "Azure CLI Tools - Azure CLI, PowerShell and Terraform",
      "source_code_type": "GitHub"
    },
    {
      "repo_url": "https://dev.azure.com/azclitools/internal/_git/azclitools-automation",
      "service_id": "092c677a-6386-4fa8-a485-991d3f9aa010",
      "service_name": "Azure CLI Tools - Azure CLI, PowerShell and Terraform",
      "source_code_type": "Azure DevOps Git"
    },
    {
      "repo_url": "https://github.com/Azure/azure-powershell-pr",
      "service_id": "092c677a-6386-4fa8-a485-991d3f9aa010",
      "service_name": "Azure CLI Tools - Azure CLI, PowerShell and Terraform",
      "source_code_type": "GitHub"
    },
    {
      "repo_url": "https://github.com/Azure/azure-powershell",
      "service_id": "092c677a-6386-4fa8-a485-991d3f9aa010",
      "service_name": "Azure CLI Tools - Azure CLI, PowerShell and Terraform",
      "source_code_type": "GitHub"
    },
    {
      "repo_url": "https://github.com/Azure/cirrus",
      "service_id": "092c677a-6386-4fa8-a485-991d3f9aa010",
      "service_name": "Azure CLI Tools - Azure CLI, PowerShell and Terraform",
      "source_code_type": "GitHub"
    },
    {
      "repo_url": "https://github.com/microsoft/terraform-provider-msgraph",
      "service_id": "092c677a-6386-4fa8-a485-991d3f9aa010",
      "service_name": "Azure CLI Tools - Azure CLI, PowerShell and Terraform",
      "source_code_type": "GitHub"
    },
    {
      "repo_url": "https://dev.azure.com/msazure/One/_git/test_azclitools",
      "service_id": "092c677a-6386-4fa8-a485-991d3f9aa010",
      "service_name": "Azure CLI Tools - Azure CLI, PowerShell and Terraform",
      "source_code_type": "Azure DevOps Git"
    },
    {
      "repo_url": "https://github.com/Azure/terraform-azurerm-hubnetworking",
      "service_id": "092c677a-6386-4fa8-a485-991d3f9aa010",
      "service_name": "Azure CLI Tools - Azure CLI, PowerShell and Terraform",
      "source_code_type": "GitHub"
    },
    {
      "repo_url": "https://github.com/Azure/TerraformModuleTelemetryService",
      "service_id": "092c677a-6386-4fa8-a485-991d3f9aa010",
      "service_name": "Azure CLI Tools - Azure CLI, PowerShell and Terraform",
      "source_code_type": "GitHub"
    },
    {
      "repo_url": "https://github.com/Azure/cli",
      "service_id": "092c677a-6386-4fa8-a485-991d3f9aa010",
      "service_name": "Azure CLI Tools - Azure CLI, PowerShell and Terraform",
      "source_code_type": "GitHub"
    },
    {
      "repo_url": "https://github.com/Azure/autorest.az",
      "service_id": "092c677a-6386-4fa8-a485-991d3f9aa010",
      "service_name": "Azure CLI Tools - Azure CLI, PowerShell and Terraform",
      "source_code_type": "GitHub"
    },
    {
      "repo_url": "https://github.com/Azure/azure-xplat-cli",
      "service_id": "092c677a-6386-4fa8-a485-991d3f9aa010",
      "service_name": "Azure CLI Tools - Azure CLI, PowerShell and Terraform",
      "source_code_type": "GitHub"
    },
    {
      "repo_url": "https://dev.azure.com/azclitools/internal/_git/azure-powershell-sanitizer",
      "service_id": "092c677a-6386-4fa8-a485-991d3f9aa010",
      "service_name": "Azure CLI Tools - Azure CLI, PowerShell and Terraform",
      "source_code_type": "Azure DevOps Git"
    },
    {
      "repo_url": "https://github.com/Azure/ms-terraform-lsp",
      "service_id": "092c677a-6386-4fa8-a485-991d3f9aa010",
      "service_name": "Azure CLI Tools - Azure CLI, PowerShell and Terraform",
      "source_code_type": "GitHub"
    },
    {
      "repo_url": "https://dev.azure.com/azclitools/release/_git/azapi2azurerm-release",
      "service_id": "092c677a-6386-4fa8-a485-991d3f9aa010",
      "service_name": "Azure CLI Tools - Azure CLI, PowerShell and Terraform",
      "source_code_type": "Azure DevOps Git"
    },
    {
      "repo_url": "https://dev.azure.com/msazure/One/_git/AzureCliTools-Wiki",
      "service_id": "092c677a-6386-4fa8-a485-991d3f9aa010",
      "service_name": "Azure CLI Tools - Azure CLI, PowerShell and Terraform",
      "source_code_type": "Azure DevOps Git"
    },
    {
      "repo_url": "https://github.com/Azure/terraform-azure-container-apps",
      "service_id": "092c677a-6386-4fa8-a485-991d3f9aa010",
      "service_name": "Azure CLI Tools - Azure CLI, PowerShell and Terraform",
      "source_code_type": "GitHub"
    },
    {
      "repo_url": "https://dev.azure.com/azclitools/internal/_git/zelinwangtestrepo",
      "service_id": "092c677a-6386-4fa8-a485-991d3f9aa010",
      "service_name": "Azure CLI Tools - Azure CLI, PowerShell and Terraform",
      "source_code_type": "Azure DevOps Git"
    },
    {
      "repo_url": "https://dev.azure.com/azclitools/release/_git/ansible-release",
      "service_id": "092c677a-6386-4fa8-a485-991d3f9aa010",
      "service_name": "Azure CLI Tools - Azure CLI, PowerShell and Terraform",
      "source_code_type": "Azure DevOps Git"
    },
    {
      "repo_url": "https://dev.azure.com/azclitools/internal/_git/azcli-code-copilot",
      "service_id": "092c677a-6386-4fa8-a485-991d3f9aa010",
      "service_name": "Azure CLI Tools - Azure CLI, PowerShell and Terraform",
      "source_code_type": "Azure DevOps Git"
    },
    {
      "repo_url": "https://dev.azure.com/azclitools/internal/_git/azure-cli-cfs",
      "service_id": "092c677a-6386-4fa8-a485-991d3f9aa010",
      "service_name": "Azure CLI Tools - Azure CLI, PowerShell and Terraform",
      "source_code_type": "Azure DevOps Git"
    },
    {
      "repo_url": "https://dev.azure.com/azclitools/release/_git/yantestrepo",
      "service_id": "092c677a-6386-4fa8-a485-991d3f9aa010",
      "service_name": "Azure CLI Tools - Azure CLI, PowerShell and Terraform",
      "source_code_type": "Azure DevOps Git"
    },
    {
      "repo_url": "https://github.com/Azure/aztfexport",
      "service_id": "092c677a-6386-4fa8-a485-991d3f9aa010",
      "service_name": "Azure CLI Tools - Azure CLI, PowerShell and Terraform",
      "source_code_type": "GitHub"
    },
    {
      "repo_url": "https://github.com/Azure/terraform-azure-modules",
      "service_id": "092c677a-6386-4fa8-a485-991d3f9aa010",
      "service_name": "Azure CLI Tools - Azure CLI, PowerShell and Terraform",
      "source_code_type": "GitHub"
    },
    {
      "repo_url": "https://github.com/Azure/tfmod-scaffold",
      "service_id": "092c677a-6386-4fa8-a485-991d3f9aa010",
      "service_name": "Azure CLI Tools - Azure CLI, PowerShell and Terraform",
      "source_code_type": "GitHub"
    },
    {
      "repo_url": "https://github.com/Azure/cli-translator",
      "service_id": "092c677a-6386-4fa8-a485-991d3f9aa010",
      "service_name": "Azure CLI Tools - Azure CLI, PowerShell and Terraform",
      "source_code_type": "GitHub"
    },
    {
      "repo_url": "https://github.com/Azure/terraform-verified-module",
      "service_id": "092c677a-6386-4fa8-a485-991d3f9aa010",
      "service_name": "Azure CLI Tools - Azure CLI, PowerShell and Terraform",
      "source_code_type": "GitHub"
    },
    {
      "repo_url": "https://dev.azure.com/azclitools/internal/_git/azure-client-tools-insights",
      "service_id": "092c677a-6386-4fa8-a485-991d3f9aa010",
      "service_name": "Azure CLI Tools - Azure CLI, PowerShell and Terraform",
      "source_code_type": "Azure DevOps Git"
    },
    {
      "repo_url": "https://dev.azure.com/azclitools/internal/_git/azure-client-tools-bot",
      "service_id": "092c677a-6386-4fa8-a485-991d3f9aa010",
      "service_name": "Azure CLI Tools - Azure CLI, PowerShell and Terraform",
      "source_code_type": "Azure DevOps Git"
    },
    {
      "repo_url": "https://github.com/Azure/homebrew-azure-cli",
      "service_id": "092c677a-6386-4fa8-a485-991d3f9aa010",
      "service_name": "Azure CLI Tools - Azure CLI, PowerShell and Terraform",
      "source_code_type": "GitHub"
    },
    {
      "repo_url": "https://github.com/Azure/autorest.powershell",
      "service_id": "092c677a-6386-4fa8-a485-991d3f9aa010",
      "service_name": "Azure CLI Tools - Azure CLI, PowerShell and Terraform",
      "source_code_type": "GitHub"
    },
    {
      "repo_url": "https://dev.azure.com/azclitools/internal/_git/tf-ai-frontend",
      "service_id": "092c677a-6386-4fa8-a485-991d3f9aa010",
      "service_name": "Azure CLI Tools - Azure CLI, PowerShell and Terraform",
      "source_code_type": "Azure DevOps Git"
    },
    {
      "repo_url": "https://github.com/Azure/terraform-azurerm-virtual-machine",
      "service_id": "092c677a-6386-4fa8-a485-991d3f9aa010",
      "service_name": "Azure CLI Tools - Azure CLI, PowerShell and Terraform",
      "source_code_type": "GitHub"
    },
    {
      "repo_url": "https://dev.azure.com/azclitools/release/_git/azurerm-lsp-release",
      "service_id": "092c677a-6386-4fa8-a485-991d3f9aa010",
      "service_name": "Azure CLI Tools - Azure CLI, PowerShell and Terraform",
      "source_code_type": "Azure DevOps Git"
    },
    {
      "repo_url": "https://dev.azure.com/msazure/One/_git/azcli-resource-notification",
      "service_id": "092c677a-6386-4fa8-a485-991d3f9aa010",
      "service_name": "Azure CLI Tools - Azure CLI, PowerShell and Terraform",
      "source_code_type": "Azure DevOps Git"
    },
    {
      "repo_url": "https://dev.azure.com/azclitools/internal/_git/AzPSModuleDiffTool",
      "service_id": "092c677a-6386-4fa8-a485-991d3f9aa010",
      "service_name": "Azure CLI Tools - Azure CLI, PowerShell and Terraform",
      "source_code_type": "Azure DevOps Git"
    },
    {
      "repo_url": "https://github.com/Azure/powershell",
      "service_id": "092c677a-6386-4fa8-a485-991d3f9aa010",
      "service_name": "Azure CLI Tools - Azure CLI, PowerShell and Terraform",
      "source_code_type": "GitHub"
    },
    {
      "repo_url": "https://github.com/Azure/azure-xplat-cli-pr",
      "service_id": "092c677a-6386-4fa8-a485-991d3f9aa010",
      "service_name": "Azure CLI Tools - Azure CLI, PowerShell and Terraform",
      "source_code_type": "GitHub"
    },
    {
      "repo_url": "https://dev.azure.com/azclitools/internal/_git/bami-tenant-management",
      "service_id": "092c677a-6386-4fa8-a485-991d3f9aa010",
      "service_name": "Azure CLI Tools - Azure CLI, PowerShell and Terraform",
      "source_code_type": "Azure DevOps Git"
    },
    {
      "repo_url": "https://dev.azure.com/azclitools/internal/_git/terraform-provider-azurerm-oidc-test",
      "service_id": "092c677a-6386-4fa8-a485-991d3f9aa010",
      "service_name": "Azure CLI Tools - Azure CLI, PowerShell and Terraform",
      "source_code_type": "Azure DevOps Git"
    }
  ],
  "subscription_count": 1
}
```

## 🔍 Evidence Queries

### k1.recent_active_outages
- **Rows returned**: 1
- **Parameters**:
```json
{
  "serviceName": "Azure CLI Tools - Azure CLI, PowerShell and Terraform"
}
```
- **Sample rows** (first 1):
```json
[
  {
    "recent_active_outages": 0
  }
]
```

### k4.avg_mttm
- **Rows returned**: 1
- **Parameters**:
```json
{
  "serviceName": "Azure CLI Tools - Azure CLI, PowerShell and Terraform"
}
```
- **Sample rows** (first 1):
```json
[
  {
    "avg_mttm_minutes": 21617
  }
]
```

### k5.outages_180d
- **Rows returned**: 1
- **Parameters**:
```json
{
  "serviceName": "Azure CLI Tools - Azure CLI, PowerShell and Terraform"
}
```
- **Sample rows** (first 1):
```json
[
  {
    "historical_outages_180d": 1
  }
]
```

### k6.related_incidents
- **Rows returned**: 1
- **Parameters**:
```json
{
  "serviceName": "Azure CLI Tools - Azure CLI, PowerShell and Terraform"
}
```
- **Sample rows** (first 1):
```json
[
  {
    "related_incidents": 0
  }
]
```

### k8.deployment_count_30d
- **Rows returned**: 1
- **Parameters**:
```json
{
  "serviceName": "Azure CLI Tools - Azure CLI, PowerShell and Terraform"
}
```
- **Sample rows** (first 1):
```json
[
  {
    "deployment_count_30d": 0
  }
]
```

### k14.safefly_caused_outages
- **Rows returned**: 1
- **Parameters**:
```json
{
  "serviceName": "Azure CLI Tools - Azure CLI, PowerShell and Terraform"
}
```
- **Sample rows** (first 1):
```json
[
  {
    "safefly_caused_outages_180d": 0
  }
]
```

### k15.sev12_incidents
- **Rows returned**: 1
- **Parameters**:
```json
{
  "serviceName": "Azure CLI Tools - Azure CLI, PowerShell and Terraform"
}
```
- **Sample rows** (first 1):
```json
[
  {
    "sev12_incident_count": 1
  }
]
```

### k7.service_tree_lookup
- **Rows returned**: 1
- **Parameters**:
```json
{
  "serviceName": "Azure CLI Tools - Azure CLI, PowerShell and Terraform"
}
```
- **Sample rows** (first 1):
```json
[
  {
    "IsExternalFacing": true,
    "Organization": "Azure Portal and Client Tools (RUHIM)",
    "ServiceId": "092c677a-6386-4fa8-a485-991d3f9aa010",
    "ServiceLevel": "Service",
    "ServiceLifecycleStage": {
      "Public": "GA"
    },
    "ServiceName": "Azure CLI Tools - Azure CLI, PowerShell and Terraform",
    "ShortName": "AzCLITools"
  }
]
```

### k10.service_subscriptions
- **Rows returned**: 9
- **Parameters**:
```json
{
  "serviceId": "092c677a-6386-4fa8-a485-991d3f9aa010"
}
```
- **Sample rows** (first 5):
```json
[
  {
    "Environment": "NonProd",
    "ServiceId": "092c677a-6386-4fa8-a485-991d3f9aa010",
    "ServiceName": "Azure CLI Tools - Azure CLI, PowerShell and Terraform",
    "Status": 1,
    "SubscriptionId": "0576f15f-eb64-41d3-99a2-e28f38ccd53c",
    "SubscriptionName": "Azure Verified Module Terraform"
  },
  {
    "Environment": "Prod",
    "ServiceId": "092c677a-6386-4fa8-a485-991d3f9aa010",
    "ServiceName": "Azure CLI Tools - Azure CLI, PowerShell and Terraform",
    "Status": 1,
    "SubscriptionId": "732d0b2b-89f0-42b4-b652-53f7253afaab",
    "SubscriptionName": "Azure Management Experience Infra"
  },
  {
    "Environment": "NonProd",
    "ServiceId": "092c677a-6386-4fa8-a485-991d3f9aa010",
    "ServiceName": "Azure CLI Tools - Azure CLI, PowerShell and Terraform",
    "Status": 1,
    "SubscriptionId": "85b3dbca-5974-4067-9669-67a141095a76",
    "SubscriptionName": "Terraform Testing on Azure with TTL = 2 Days"
  },
  {
    "Environment": "NonProd",
    "ServiceId": "092c677a-6386-4fa8-a485-991d3f9aa010",
    "ServiceName": "Azure CLI Tools - Azure CLI, PowerShell and Terraform",
    "Status": 1,
    "SubscriptionId": "9e223dbe-3399-4e19-88eb-0975f02ac87f",
    "SubscriptionName": "Azure SDK Powershell Test - Manual"
  },
  {
    "Environment": "NonProd",
    "ServiceId": "092c677a-6386-4fa8-a485-991d3f9aa010",
    "ServiceName": "Azure CLI Tools - Azure CLI, PowerShell and Terraform",
    "Status": 1,
    "SubscriptionId": "f64d4ee8-be94-457d-ba26-3fa6b6506cef",
    "SubscriptionName": "OSS Integration DevINT with TTL = 7 Days"
  }
]
```

### k12.service_repos
- **Rows returned**: 50
- **Parameters**:
```json
{
  "serviceId": "092c677a-6386-4fa8-a485-991d3f9aa010"
}
```
- **Sample rows** (first 5):
```json
[
  {
    "RepoUrl": "https://github.com/Azure/azure-cli-pr",
    "ServiceId": "092c677a-6386-4fa8-a485-991d3f9aa010",
    "ServiceName": "Azure CLI Tools - Azure CLI, PowerShell and Terraform",
    "SourceCodeType": "GitHub"
  },
  {
    "RepoUrl": "https://github.com/Azure/terraform-azure-azureacademy-avd-lab",
    "ServiceId": "092c677a-6386-4fa8-a485-991d3f9aa010",
    "ServiceName": "Azure CLI Tools - Azure CLI, PowerShell and Terraform",
    "SourceCodeType": "GitHub"
  },
  {
    "RepoUrl": "https://github.com/microsoft/msgraph-vscode",
    "ServiceId": "092c677a-6386-4fa8-a485-991d3f9aa010",
    "ServiceName": "Azure CLI Tools - Azure CLI, PowerShell and Terraform",
    "SourceCodeType": "GitHub"
  },
  {
    "RepoUrl": "https://dev.azure.com/azclitools/release/_git/vscode-azureterraform-release",
    "ServiceId": "092c677a-6386-4fa8-a485-991d3f9aa010",
    "ServiceName": "Azure CLI Tools - Azure CLI, PowerShell and Terraform",
    "SourceCodeType": "Azure DevOps Git"
  },
  {
    "RepoUrl": "https://dev.azure.com/azclitools/internal/_git/test-cli-upload",
    "ServiceId": "092c677a-6386-4fa8-a485-991d3f9aa010",
    "ServiceName": "Azure CLI Tools - Azure CLI, PowerShell and Terraform",
    "SourceCodeType": "Azure DevOps Git"
  }
]
```

### k13.arg_peer_resources
- **Rows returned**: 1
- **Parameters**:
```json
{
  "resourceGroupName": "azclis-copilot-rg-beta",
  "subscriptionId": "6b085460-5f21-477e-ba44-1035046e9101"
}
```
- **Sample rows** (first 1):
```json
[
  {
    "peer_resource_count": 48
  }
]
```

## ❓ Unknowns

*All required data points were available.*

