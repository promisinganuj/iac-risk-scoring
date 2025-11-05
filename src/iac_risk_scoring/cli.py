"""Command-line interface for IaC risk scoring."""
import sys
import json
import argparse
from pathlib import Path
from typing import Optional
from .risk_scorer import RiskScorer


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Score risks in Infrastructure as Code changes for Azure"
    )
    parser.add_argument(
        "path",
        help="Path to IaC file or directory to analyze"
    )
    parser.add_argument(
        "-f", "--format",
        choices=["json", "text"],
        default="text",
        help="Output format (default: text)"
    )
    parser.add_argument(
        "-o", "--output",
        help="Output file path (default: stdout)"
    )
    parser.add_argument(
        "--fail-on",
        choices=["critical", "high", "medium", "low"],
        help="Exit with error code if risk level meets or exceeds this threshold"
    )
    
    args = parser.parse_args()
    
    try:
        # Initialize scorer
        scorer = RiskScorer()
        
        # Score the input
        path = Path(args.path)
        if path.is_file():
            result = scorer.score_file(str(path))
        elif path.is_dir():
            result = scorer.score_directory(str(path))
        else:
            print(f"Error: Path not found: {args.path}", file=sys.stderr)
            sys.exit(1)
        
        # Format output
        if args.format == "json":
            output = json.dumps(result.to_dict(), indent=2)
        else:
            output = format_text_output(result)
        
        # Write output
        if args.output:
            Path(args.output).write_text(output, encoding='utf-8')
            print(f"Results written to {args.output}")
        else:
            print(output)
        
        # Check fail threshold
        if args.fail_on:
            risk_levels = ["info", "low", "medium", "high", "critical"]
            threshold_idx = risk_levels.index(args.fail_on)
            result_idx = risk_levels.index(result.risk_level.value)
            
            if result_idx >= threshold_idx:
                sys.exit(1)
        
        sys.exit(0)
        
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def format_text_output(result) -> str:
    """Format risk score as human-readable text."""
    lines = []
    
    lines.append("=" * 70)
    lines.append("IaC Risk Scoring Report")
    lines.append("=" * 70)
    lines.append("")
    
    lines.append(f"Overall Risk Score: {result.total_score}/100")
    lines.append(f"Risk Level: {result.risk_level.value.upper()}")
    lines.append("")
    
    lines.append("Summary:")
    lines.append(f"  Total Findings: {result.summary['total_findings']}")
    lines.append("")
    
    lines.append("By Severity:")
    for level in ["critical", "high", "medium", "low", "info"]:
        count = result.summary['by_level'][level]
        if count > 0:
            lines.append(f"  {level.capitalize()}: {count}")
    lines.append("")
    
    lines.append("By Category:")
    for category in ["security", "compliance", "reliability", "cost", "performance"]:
        count = result.summary['by_category'][category]
        if count > 0:
            lines.append(f"  {category.capitalize()}: {count}")
    lines.append("")
    
    if result.findings:
        lines.append("=" * 70)
        lines.append("Detailed Findings:")
        lines.append("=" * 70)
        lines.append("")
        
        for idx, finding in enumerate(result.findings, 1):
            lines.append(f"{idx}. [{finding.level.value.upper()}] {finding.title}")
            lines.append(f"   Rule: {finding.rule_id}")
            lines.append(f"   Resource: {finding.resource_name} ({finding.resource_type})")
            lines.append(f"   Category: {finding.category.value}")
            lines.append(f"   Description: {finding.description}")
            lines.append(f"   Remediation: {finding.remediation}")
            lines.append("")
    else:
        lines.append("No issues found! Your IaC templates look good.")
        lines.append("")
    
    lines.append("=" * 70)
    
    return "\n".join(lines)


if __name__ == "__main__":
    main()
