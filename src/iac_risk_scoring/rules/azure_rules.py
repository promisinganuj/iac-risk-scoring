"""Azure-specific risk assessment rules."""
from typing import Optional, List
from .base import RiskRule
from ..models import IaCResource, RiskFinding, RiskLevel, RiskCategory


class PublicIPRule(RiskRule):
    """Check for publicly exposed resources."""

    def __init__(self):
        super().__init__()
        self.rule_id = "AZ-SEC-001"
        self.title = "Public IP Address Assignment"
        self.description = "Resource has a public IP address which may expose it to the internet"
        self.remediation = "Review if public access is necessary. Use private endpoints where possible."

    def evaluate(self, resource: IaCResource) -> Optional[RiskFinding]:
        properties = resource.properties
        
        # Check for public IP assignment
        if 'publicIPAddress' in properties or 'publicIpAddress' in properties:
            return RiskFinding(
                category=RiskCategory.SECURITY,
                level=RiskLevel.HIGH,
                resource_type=resource.resource_type,
                resource_name=resource.name,
                rule_id=self.rule_id,
                title=self.title,
                description=self.description,
                remediation=self.remediation,
                location=resource.location,
            )
        
        # Check for public network access setting
        public_access = properties.get('publicNetworkAccess', 'Disabled')
        if public_access == 'Enabled':
            return RiskFinding(
                category=RiskCategory.SECURITY,
                level=RiskLevel.HIGH,
                resource_type=resource.resource_type,
                resource_name=resource.name,
                rule_id=self.rule_id,
                title=self.title,
                description=self.description,
                remediation=self.remediation,
                location=resource.location,
            )
        
        return None

    def applies_to(self, resource_type: str) -> bool:
        applicable_types = [
            'Microsoft.Compute/virtualMachines',
            'Microsoft.Network/networkInterfaces',
            'Microsoft.Network/publicIPAddresses',
            'Microsoft.Storage/storageAccounts',
            'Microsoft.Sql/servers',
            'azurerm_public_ip',
            'azurerm_virtual_machine',
            'azurerm_network_interface',
        ]
        return any(rt in resource_type for rt in applicable_types)


class StorageEncryptionRule(RiskRule):
    """Check for storage encryption."""

    def __init__(self):
        super().__init__()
        self.rule_id = "AZ-SEC-002"
        self.title = "Storage Encryption Not Enabled"
        self.description = "Storage account does not have encryption enabled"
        self.remediation = "Enable encryption at rest for storage accounts using Azure Storage Service Encryption."

    def evaluate(self, resource: IaCResource) -> Optional[RiskFinding]:
        if not self.applies_to(resource.resource_type):
            return None
            
        properties = resource.properties
        encryption = properties.get('encryption', {})
        
        # Check if encryption is disabled
        if isinstance(encryption, dict):
            services = encryption.get('services', {})
            if not services:
                return RiskFinding(
                    category=RiskCategory.SECURITY,
                    level=RiskLevel.CRITICAL,
                    resource_type=resource.resource_type,
                    resource_name=resource.name,
                    rule_id=self.rule_id,
                    title=self.title,
                    description=self.description,
                    remediation=self.remediation,
                    location=resource.location,
                )
            
            # Check if any service is enabled - services can be boolean or dict with 'enabled' key
            has_encryption = False
            for service in services.values():
                if isinstance(service, bool) and service:
                    has_encryption = True
                    break
                elif isinstance(service, dict) and service.get('enabled'):
                    has_encryption = True
                    break
            
            if not has_encryption:
                return RiskFinding(
                    category=RiskCategory.SECURITY,
                    level=RiskLevel.CRITICAL,
                    resource_type=resource.resource_type,
                    resource_name=resource.name,
                    rule_id=self.rule_id,
                    title=self.title,
                    description=self.description,
                    remediation=self.remediation,
                    location=resource.location,
                )
        
        return None

    def applies_to(self, resource_type: str) -> bool:
        return 'storage' in resource_type.lower()


class HTTPSOnlyRule(RiskRule):
    """Check for HTTPS-only enforcement."""

    def __init__(self):
        super().__init__()
        self.rule_id = "AZ-SEC-003"
        self.title = "HTTPS Not Enforced"
        self.description = "Resource does not enforce HTTPS-only connections"
        self.remediation = "Enable HTTPS-only mode to ensure encrypted connections."

    def evaluate(self, resource: IaCResource) -> Optional[RiskFinding]:
        if not self.applies_to(resource.resource_type):
            return None
            
        properties = resource.properties
        
        # Check for supportsHttpsTrafficOnly or enable_https_traffic_only
        https_only = properties.get('supportsHttpsTrafficOnly', 
                                    properties.get('enable_https_traffic_only', True))
        
        if https_only is False:
            return RiskFinding(
                category=RiskCategory.SECURITY,
                level=RiskLevel.HIGH,
                resource_type=resource.resource_type,
                resource_name=resource.name,
                rule_id=self.rule_id,
                title=self.title,
                description=self.description,
                remediation=self.remediation,
                location=resource.location,
            )
        
        return None

    def applies_to(self, resource_type: str) -> bool:
        applicable_types = ['storage', 'webapp', 'functionapp', 'app_service']
        return any(t in resource_type.lower() for t in applicable_types)


class TLSVersionRule(RiskRule):
    """Check for minimum TLS version."""

    def __init__(self):
        super().__init__()
        self.rule_id = "AZ-SEC-004"
        self.title = "Weak TLS Version"
        self.description = "Resource uses an outdated TLS version (< 1.2)"
        self.remediation = "Configure minimum TLS version to 1.2 or higher."

    def evaluate(self, resource: IaCResource) -> Optional[RiskFinding]:
        if not self.applies_to(resource.resource_type):
            return None
            
        properties = resource.properties
        
        # Check TLS version
        min_tls = properties.get('minimumTlsVersion', 
                                properties.get('min_tls_version', 'TLS1_2'))
        
        weak_versions = ['TLS1_0', 'TLS1_1', '1.0', '1.1']
        if any(weak in str(min_tls) for weak in weak_versions):
            return RiskFinding(
                category=RiskCategory.SECURITY,
                level=RiskLevel.HIGH,
                resource_type=resource.resource_type,
                resource_name=resource.name,
                rule_id=self.rule_id,
                title=self.title,
                description=self.description,
                remediation=self.remediation,
                location=resource.location,
            )
        
        return None

    def applies_to(self, resource_type: str) -> bool:
        applicable_types = ['storage', 'sql', 'mysql', 'postgresql', 'webapp']
        return any(t in resource_type.lower() for t in applicable_types)


class AzureSecurityRules:
    """Collection of Azure security rules."""

    @staticmethod
    def get_all_rules() -> List[RiskRule]:
        """Get all available security rules."""
        return [
            PublicIPRule(),
            StorageEncryptionRule(),
            HTTPSOnlyRule(),
            TLSVersionRule(),
        ]
