"""Parser for Terraform configurations."""
import re
from typing import List, Dict, Any
from .base import IaCParser
from ..models import IaCResource


class TerraformParser(IaCParser):
    """Parser for Terraform configurations (simple HCL parsing)."""

    def parse(self, template_content: str) -> List[IaCResource]:
        """
        Parse Terraform configuration and extract Azure resources.
        
        Args:
            template_content: Terraform HCL content
            
        Returns:
            List of IaCResource objects
        """
        resources = []
        
        # Simple regex-based parsing for Terraform resources
        # Pattern: resource "type" "name" { ... }
        resource_pattern = r'resource\s+"([^"]+)"\s+"([^"]+)"\s*\{([^}]*(?:\{[^}]*\}[^}]*)*)\}'
        
        for match in re.finditer(resource_pattern, template_content, re.DOTALL):
            resource_type = match.group(1)
            resource_name = match.group(2)
            resource_body = match.group(3)
            
            # Only process Azure resources (starting with azurerm_)
            if not resource_type.startswith('azurerm_'):
                continue
            
            properties = self._parse_properties(resource_body)
            
            iac_resource = IaCResource(
                resource_type=resource_type,
                name=resource_name,
                properties=properties,
                location={
                    "line": template_content[:match.start()].count('\n') + 1,
                    "file": "main.tf"
                },
                metadata={
                    "provider": "azurerm"
                }
            )
            resources.append(iac_resource)
        
        return resources

    def _parse_properties(self, body: str) -> Dict[str, Any]:
        """Extract properties from resource body (simplified)."""
        properties = {}
        
        # Simple key-value parsing
        simple_property_pattern = r'(\w+)\s*=\s*"([^"]*)"'
        for match in re.finditer(simple_property_pattern, body):
            key = match.group(1)
            value = match.group(2)
            properties[key] = value
        
        # Boolean values
        bool_pattern = r'(\w+)\s*=\s*(true|false)'
        for match in re.finditer(bool_pattern, body):
            key = match.group(1)
            value = match.group(2) == 'true'
            properties[key] = value
        
        return properties

    def supports_file(self, filename: str) -> bool:
        """Check if this is a Terraform file."""
        return filename.endswith('.tf')
