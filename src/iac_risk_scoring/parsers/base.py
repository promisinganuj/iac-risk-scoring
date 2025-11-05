"""Base parser interface for IaC templates."""
from abc import ABC, abstractmethod
from typing import List, Dict, Any
from ..models import IaCResource


class IaCParser(ABC):
    """Base class for IaC parsers."""

    @abstractmethod
    def parse(self, template_content: str) -> List[IaCResource]:
        """
        Parse IaC template and extract resources.
        
        Args:
            template_content: The IaC template content as string
            
        Returns:
            List of IaCResource objects
        """
        pass

    @abstractmethod
    def supports_file(self, filename: str) -> bool:
        """
        Check if parser supports the given file.
        
        Args:
            filename: Name of the file to check
            
        Returns:
            True if parser can handle this file
        """
        pass
