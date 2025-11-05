# IaC Risk Scoring

A comprehensive tool for performing risk scoring on Infrastructure as Code (IaC) changes for Azure Cloud Infrastructure. This tool helps identify security, compliance, and reliability issues in ARM templates and Terraform configurations before deployment.

## Features

- **Multi-format Support**: Parse and analyze both ARM templates (JSON) and Terraform configurations
- **Azure-Focused**: Specialized rules for Azure resource security and best practices
- **Comprehensive Risk Assessment**: Evaluate resources across multiple categories:
  - Security (public access, encryption, HTTPS enforcement)
  - Compliance (TLS versions, access controls)
  - Reliability
  - Cost optimization
  - Performance
- **Flexible Output**: JSON or human-readable text output
- **CI/CD Integration**: Exit codes based on risk thresholds for pipeline integration
- **Extensible**: Easy to add custom rules and parsers

## Installation

### From source

```bash
git clone https://github.com/promisinganuj/iac-risk-scoring.git
cd iac-risk-scoring
pip install -e .
```

### Development installation

```bash
pip install -e ".[dev]"
```

## Usage

### Command Line

Score a single file:
```bash
iac-risk-score path/to/template.json
```

Score a directory:
```bash
iac-risk-score path/to/templates/
```

Output as JSON:
```bash
iac-risk-score template.json --format json
```

Save output to file:
```bash
iac-risk-score template.json --output report.txt
```

Fail on high risk or above (useful in CI/CD):
```bash
iac-risk-score template.json --fail-on high
```

### Python API

```python
from iac_risk_scoring import RiskScorer

# Initialize scorer
scorer = RiskScorer()

# Score a file
result = scorer.score_file("template.json")

# Score template content directly
template_content = """
{
  "resources": [...]
}
"""
result = scorer.score_template(template_content, file_type="json")

# Access results
print(f"Risk Score: {result.total_score}/100")
print(f"Risk Level: {result.risk_level.value}")
print(f"Findings: {len(result.findings)}")

for finding in result.findings:
    print(f"- [{finding.level.value}] {finding.title}")
```

## Risk Rules

### Security Rules

1. **AZ-SEC-001: Public IP Address Assignment**
   - Detects resources with public IP addresses
   - Risk Level: HIGH
   - Applies to: VMs, Network Interfaces, Storage Accounts, SQL Servers

2. **AZ-SEC-002: Storage Encryption Not Enabled**
   - Checks for encryption at rest configuration
   - Risk Level: CRITICAL
   - Applies to: Storage Accounts

3. **AZ-SEC-003: HTTPS Not Enforced**
   - Verifies HTTPS-only connections are enforced
   - Risk Level: HIGH
   - Applies to: Storage Accounts, Web Apps, Function Apps

4. **AZ-SEC-004: Weak TLS Version**
   - Checks for minimum TLS 1.2 configuration
   - Risk Level: HIGH
   - Applies to: Storage, SQL, MySQL, PostgreSQL, Web Apps

## Risk Levels

- **CRITICAL** (100 points): Severe security vulnerabilities requiring immediate attention
- **HIGH** (75 points): Significant security or compliance issues
- **MEDIUM** (50 points): Moderate risks that should be addressed
- **LOW** (25 points): Minor issues or best practice violations
- **INFO** (0 points): Informational findings

## Examples

### ARM Template Example

```json
{
  "resources": [
    {
      "type": "Microsoft.Storage/storageAccounts",
      "name": "mystorageaccount",
      "properties": {
        "supportsHttpsTrafficOnly": true,
        "minimumTlsVersion": "TLS1_2",
        "encryption": {
          "services": {
            "blob": {"enabled": true}
          }
        }
      }
    }
  ]
}
```

### Terraform Example

```hcl
resource "azurerm_storage_account" "example" {
  name                     = "mystorageaccount"
  enable_https_traffic_only = true
  min_tls_version          = "TLS1_2"
}
```

See the `examples/` directory for more sample templates.

## Development

### Running Tests

```bash
pytest
```

With coverage:
```bash
pytest --cov=iac_risk_scoring --cov-report=html
```

### Code Quality

```bash
# Format code
black src/ tests/

# Lint
flake8 src/ tests/

# Type checking
mypy src/
```

## Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch
3. Add tests for new functionality
4. Ensure all tests pass
5. Submit a pull request

## License

MIT License - see LICENSE file for details

## Support

For issues, questions, or contributions, please open an issue on GitHub.
