"""Parser for Azure ARM templates."""
import json
from typing import List, Dict, Any
from .base import IaCParser
from ..models import IaCResource


class ARMParser(IaCParser):
    """Parser for Azure Resource Manager (ARM) templates."""

    def parse(self, template_content: str) -> List[IaCResource]:
        """
        Parse ARM template and extract resources.
        
        Args:
            template_content: ARM template JSON content
            
        Returns:
            List of IaCResource objects
        """
        try:
            template = json.loads(template_content)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in ARM template: {e}")

        if not isinstance(template, dict):
            raise ValueError("ARM template must be a JSON object")

        resources = []
        arm_resources = template.get("resources", [])

        for idx, resource in enumerate(arm_resources):
            if not isinstance(resource, dict):
                continue

            resource_type = resource.get("type", "")
            resource_name = resource.get("name", f"unnamed-{idx}")
            
            iac_resource = IaCResource(
                resource_type=resource_type,
                name=resource_name,
                properties=resource.get("properties", {}),
                location={
                    "line": idx,  # Approximate location
                    "file": "template.json"
                },
                dependencies=resource.get("dependsOn", []),
                metadata={
                    "api_version": resource.get("apiVersion", ""),
                    "location": resource.get("location", ""),
                    "tags": resource.get("tags", {}),
                    "sku": resource.get("sku", {}),
                }
            )
            resources.append(iac_resource)

        return resources

    def supports_file(self, filename: str) -> bool:
        """Check if this is an ARM template file."""
        return filename.endswith(('.json', '.template.json'))
