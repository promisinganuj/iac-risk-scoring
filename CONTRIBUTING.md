# Contributing to IaC Risk Scoring

Thank you for your interest in contributing to IaC Risk Scoring! This document provides guidelines and instructions for contributing.

## Development Setup

1. Fork and clone the repository:
```bash
git clone https://github.com/your-username/iac-risk-scoring.git
cd iac-risk-scoring
```

2. Install development dependencies:
```bash
pip install -e ".[dev]"
```

3. Run tests to ensure everything is working:
```bash
pytest
```

## Development Workflow

1. Create a new branch for your feature or bugfix:
```bash
git checkout -b feature/your-feature-name
```

2. Make your changes and write tests

3. Run the test suite:
```bash
pytest tests/ -v
```

4. Check code formatting:
```bash
black src/ tests/
flake8 src/ tests/
```

5. Commit your changes:
```bash
git commit -m "Description of changes"
```

6. Push and create a pull request

## Adding New Rules

To add a new risk assessment rule:

1. Create a new rule class in `src/iac_risk_scoring/rules/azure_rules.py`:

```python
class YourNewRule(RiskRule):
    def __init__(self):
        super().__init__()
        self.rule_id = "AZ-SEC-XXX"
        self.title = "Your Rule Title"
        self.description = "Description of what this rule checks"
        self.remediation = "How to fix this issue"

    def evaluate(self, resource: IaCResource) -> Optional[RiskFinding]:
        # Your rule logic here
        pass

    def applies_to(self, resource_type: str) -> bool:
        # Which resource types this rule applies to
        pass
```

2. Add the rule to `AzureSecurityRules.get_all_rules()`

3. Write tests in `tests/rules/test_azure_rules.py`

## Adding New Parsers

To add support for a new IaC format:

1. Create a new parser in `src/iac_risk_scoring/parsers/`:

```python
from .base import IaCParser

class YourParser(IaCParser):
    def parse(self, template_content: str) -> List[IaCResource]:
        # Parse logic here
        pass

    def supports_file(self, filename: str) -> bool:
        # File extension check
        pass
```

2. Register the parser in `src/iac_risk_scoring/parsers/__init__.py`

3. Add the parser to `RiskScorer.__init__()` in `src/iac_risk_scoring/risk_scorer.py`

4. Write tests in `tests/parsers/`

## Code Style

- Follow PEP 8 guidelines
- Use type hints for function parameters and return values
- Write docstrings for all public functions and classes
- Keep functions focused and single-purpose
- Maximum line length: 100 characters

## Testing

- Write tests for all new functionality
- Maintain test coverage above 80%
- Use descriptive test names: `test_<what>_<condition>_<expected_result>`
- Include both positive and negative test cases

## Documentation

- Update README.md if adding new features
- Add docstrings to new functions and classes
- Include examples for new functionality
- Update type hints and inline comments

## Pull Request Guidelines

- Provide a clear description of the changes
- Reference any related issues
- Include test results
- Ensure CI checks pass
- Keep PRs focused on a single feature or fix

## Questions?

Feel free to open an issue for:
- Bug reports
- Feature requests
- Questions about usage or development
- Suggestions for improvement

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
