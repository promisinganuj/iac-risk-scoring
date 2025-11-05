"""Main risk scoring orchestrator."""
from typing import List, Optional
from pathlib import Path
from .models import RiskScore, IaCResource
from .parsers import ARMParser, TerraformParser, IaCParser
from .analyzers import RiskAnalyzer
from .rules import AzureSecurityRules


class RiskScorer:
    """Main class for scoring IaC risks."""

    def __init__(self, custom_rules: Optional[List] = None):
        """
        Initialize risk scorer.
        
        Args:
            custom_rules: Optional list of custom risk rules
        """
        self.parsers: List[IaCParser] = [
            ARMParser(),
            TerraformParser(),
        ]
        
        # Use custom rules if provided, otherwise use default Azure rules
        rules = custom_rules if custom_rules else AzureSecurityRules.get_all_rules()
        self.analyzer = RiskAnalyzer(rules)

    def score_file(self, file_path: str) -> RiskScore:
        """
        Score a single IaC file.
        
        Args:
            file_path: Path to the IaC file
            
        Returns:
            RiskScore for the file
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        content = path.read_text(encoding='utf-8')
        
        # Find appropriate parser
        parser = self._get_parser(path.name)
        if not parser:
            raise ValueError(f"No parser available for file: {path.name}")

        # Parse and analyze
        resources = parser.parse(content)
        return self.analyzer.analyze(resources)

    def score_template(self, template_content: str, file_type: str = "json") -> RiskScore:
        """
        Score IaC template content directly.
        
        Args:
            template_content: The IaC template content
            file_type: Type of template (json for ARM, tf for Terraform)
            
        Returns:
            RiskScore for the template
        """
        filename = f"template.{file_type}"
        parser = self._get_parser(filename)
        
        if not parser:
            raise ValueError(f"No parser available for file type: {file_type}")

        resources = parser.parse(template_content)
        return self.analyzer.analyze(resources)

    def score_directory(self, directory_path: str) -> RiskScore:
        """
        Score all IaC files in a directory.
        
        Args:
            directory_path: Path to directory containing IaC files
            
        Returns:
            Aggregated RiskScore for all files
        """
        path = Path(directory_path)
        if not path.exists() or not path.is_dir():
            raise ValueError(f"Invalid directory: {directory_path}")

        all_resources: List[IaCResource] = []
        
        # Find and parse all supported files
        for file_path in path.rglob("*"):
            if not file_path.is_file():
                continue
                
            parser = self._get_parser(file_path.name)
            if parser:
                try:
                    content = file_path.read_text(encoding='utf-8')
                    resources = parser.parse(content)
                    all_resources.extend(resources)
                except Exception as e:
                    # Log error but continue with other files
                    print(f"Warning: Failed to parse {file_path}: {e}")

        return self.analyzer.analyze(all_resources)

    def _get_parser(self, filename: str) -> Optional[IaCParser]:
        """Find appropriate parser for file."""
        for parser in self.parsers:
            if parser.supports_file(filename):
                return parser
        return None
