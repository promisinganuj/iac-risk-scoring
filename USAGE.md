# Usage Guide

This guide provides practical examples of using the IaC Risk Scoring tool.

## Quick Start

### 1. Install the tool

```bash
pip install -e .
```

### 2. Scan a single file

```bash
iac-risk-score template.json
```

### 3. Scan a directory

```bash
iac-risk-score ./infrastructure/
```

## Common Use Cases

### CI/CD Integration

Fail the build if critical or high-risk issues are found:

```bash
iac-risk-score terraform/ --fail-on high
```

This will exit with code 1 if any HIGH or CRITICAL risks are detected.

### Generate JSON Report

```bash
iac-risk-score template.json --format json --output report.json
```

### Scan Before Deployment

```bash
# Scan ARM templates
iac-risk-score azure-deploy.json

# Scan Terraform configurations
iac-risk-score main.tf
```

## Python API Examples

### Basic Usage

```python
from iac_risk_scoring import RiskScorer

# Create scorer instance
scorer = RiskScorer()

# Score a file
result = scorer.score_file("template.json")

# Print results
print(f"Risk Level: {result.risk_level.value}")
print(f"Total Score: {result.total_score}/100")
print(f"Issues Found: {len(result.findings)}")
```

### Detailed Analysis

```python
from iac_risk_scoring import RiskScorer

scorer = RiskScorer()
result = scorer.score_file("template.json")

# Print all findings
for finding in result.findings:
    print(f"\n[{finding.level.value.upper()}] {finding.title}")
    print(f"Resource: {finding.resource_name}")
    print(f"Issue: {finding.description}")
    print(f"Fix: {finding.remediation}")
```

### Export to JSON

```python
import json
from iac_risk_scoring import RiskScorer

scorer = RiskScorer()
result = scorer.score_file("template.json")

# Export to JSON file
with open("risk-report.json", "w") as f:
    json.dump(result.to_dict(), f, indent=2)
```

### Scan Multiple Files

```python
from iac_risk_scoring import RiskScorer
from pathlib import Path

scorer = RiskScorer()

# Scan all templates in a directory
template_dir = Path("./infrastructure")
all_findings = []

for template_file in template_dir.glob("*.json"):
    result = scorer.score_file(str(template_file))
    all_findings.extend(result.findings)

print(f"Total issues found: {len(all_findings)}")
```

### Custom Rules

```python
from iac_risk_scoring import RiskScorer
from iac_risk_scoring.rules.base import RiskRule
from iac_risk_scoring.models import RiskFinding, RiskLevel, RiskCategory

class CustomRule(RiskRule):
    def __init__(self):
        super().__init__()
        self.rule_id = "CUSTOM-001"
        self.title = "Custom Security Check"
        self.description = "Custom security rule"
        self.remediation = "Fix according to policy"
    
    def evaluate(self, resource):
        # Your custom logic here
        if "custom_property" not in resource.properties:
            return RiskFinding(
                category=RiskCategory.SECURITY,
                level=RiskLevel.MEDIUM,
                resource_type=resource.resource_type,
                resource_name=resource.name,
                rule_id=self.rule_id,
                title=self.title,
                description=self.description,
                remediation=self.remediation
            )
        return None
    
    def applies_to(self, resource_type):
        return True

# Use custom rule
custom_rules = [CustomRule()]
scorer = RiskScorer(custom_rules=custom_rules)
result = scorer.score_file("template.json")
```

## GitHub Actions Integration

Create `.github/workflows/iac-scan.yml`:

```yaml
name: IaC Security Scan

on:
  pull_request:
    paths:
      - '**.json'
      - '**.tf'

jobs:
  scan:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      
      - name: Install IaC Risk Scoring
        run: pip install iac-risk-scoring
      
      - name: Scan IaC templates
        run: |
          iac-risk-score infrastructure/ --format json --output scan-results.json
          iac-risk-score infrastructure/ --fail-on high
      
      - name: Upload results
        if: always()
        uses: actions/upload-artifact@v3
        with:
          name: iac-scan-results
          path: scan-results.json
```

## Azure DevOps Integration

Add to your pipeline:

```yaml
- task: UsePythonVersion@0
  inputs:
    versionSpec: '3.11'

- script: |
    pip install iac-risk-scoring
  displayName: 'Install IaC Risk Scoring'

- script: |
    iac-risk-score $(System.DefaultWorkingDirectory)/infrastructure --fail-on high
  displayName: 'Scan IaC Templates'
  continueOnError: false
```

## Best Practices

1. **Integrate Early**: Run scans as part of your CI/CD pipeline
2. **Set Appropriate Thresholds**: Use `--fail-on` to enforce security standards
3. **Regular Scans**: Scan before every deployment
4. **Track Over Time**: Store scan results to track security posture
5. **Review Findings**: Don't just fail builds - review and fix issues
6. **Custom Rules**: Add organization-specific rules for your security policies

## Troubleshooting

### Parser Errors

If you get parsing errors:
- Verify JSON syntax for ARM templates
- Check HCL syntax for Terraform files
- Ensure files have correct extensions (.json, .tf)

### No Issues Found

If scanning doesn't find expected issues:
- Verify the resource types are supported
- Check that properties are in the expected format
- Review the rule definitions for applicability

### Performance

For large directories:
- Consider scanning specific subdirectories
- Use file patterns to limit scope
- Run scans in parallel for multiple directories

## Getting Help

- Check the README.md for feature documentation
- See CONTRIBUTING.md for development guidelines
- Open an issue on GitHub for bugs or feature requests
