"""
Dependency Risk Analyzer (Single Package Analysis)
Analyzes dependency complexity and bug correlation for individual packages

Updated to use:
- Production dependencies (not total)
- Empirical terciles from correlation analysis
- Temporal mismatch awareness
"""

import json
import requests
from pathlib import Path
from collections import defaultdict


def load_empirical_thresholds():
    """
    Load empirical thresholds from correlation analysis if available
    
    Returns:
        dict with thresholds or None if not found
    """
    correlation_file = Path("correlation_data_full.json")
    
    if correlation_file.exists():
        try:
            with open(correlation_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data.get('empirical_thresholds')
        except Exception:
            pass
    
    return None


def fetch_package_json(package_name):
    """
    Fetch package.json from npm registry
    
    Note: This fetches the LATEST version, which may not reflect
    the dependency state at the time historical bugs were filed.
    See temporal_validator.py for temporal stability analysis.
    """
    url = f"https://registry.npmjs.org/{package_name}/latest"
    
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            return response.json()
        else:
            print(f"  ⚠️  Failed to fetch {package_name}: HTTP {response.status_code}")
            return None
    except Exception as e:
        print(f"  ⚠️  Error fetching {package_name}: {e}")
        return None


def count_dependencies(package_data):
    """
    Count dependencies with focus on production (runtime) dependencies
    
    Production dependencies = dependencies + peerDependencies + optionalDependencies
    These represent actual runtime exposure to external code.
    
    Development dependencies are excluded as they don't affect deployed code.
    """
    if not package_data:
        return None
    
    dependencies = package_data.get('dependencies', {})
    dev_dependencies = package_data.get('devDependencies', {})
    peer_dependencies = package_data.get('peerDependencies', {})
    optional_dependencies = package_data.get('optionalDependencies', {})
    
    # Production dependencies = runtime exposure (RISK-RELEVANT)
    production = len(dependencies) + len(peer_dependencies) + len(optional_dependencies)
    
    return {
        'direct': len(dependencies),
        'dev': len(dev_dependencies),
        'peer': len(peer_dependencies),
        'optional': len(optional_dependencies),
        'total': len(dependencies) + len(dev_dependencies) + len(peer_dependencies) + len(optional_dependencies),
        'production': production,  # ← PRIMARY METRIC
        'dependency_names': {
            'dependencies': list(dependencies.keys()),
            'devDependencies': list(dev_dependencies.keys()),
            'peerDependencies': list(peer_dependencies.keys()),
            'optionalDependencies': list(optional_dependencies.keys())
        }
    }


def load_bugs_for_package(classified_file, package_name):
    """
    Load classified bugs for a specific package from the dataset
    """
    if not Path(classified_file).exists():
        return None
    
    bugs = []
    
    with open(classified_file, 'r', encoding='utf-8') as f:
        for line in f:
            if not line.strip():
                continue
            
            try:
                issue = json.loads(line)
                
                # Check if this bug is from the target package
                repo = issue.get('repo', '')
                
                # Handle both 'owner/repo' and just 'repo' formats
                if '/' in repo:
                    repo_name = repo.split('/')[-1]
                else:
                    repo_name = repo
                
                # Match package name (case-insensitive)
                if repo_name.lower() == package_name.lower():
                    bugs.append(issue)
                    
            except json.JSONDecodeError:
                continue
    
    if not bugs:
        return None
    
    # Count by classification
    counts = defaultdict(int)
    for bug in bugs:
        classification = bug.get('final_classification', 'Unknown')
        counts[classification] += 1
    
    total = len(bugs)
    
    # Calculate ratios
    ratios = {k: (v / total * 100) if total > 0 else 0 for k, v in counts.items()}
    
    return {
        'total_bugs': total,
        'counts': dict(counts),
        'ratios': ratios,
        'bugs': bugs
    }


def assess_risk_level(prod_deps, extrinsic_ratio, empirical_thresholds=None):
    """
    Determine risk level based on PRODUCTION dependencies and extrinsic ratio
    
    Uses empirical terciles from correlation analysis if available,
    otherwise falls back to data-driven heuristics.
    
    Args:
        prod_deps: Production dependency count
        extrinsic_ratio: Percentage of extrinsic bugs (0-100)
        empirical_thresholds: Optional thresholds from correlation analysis
    
    Returns:
        str: "LOW", "MEDIUM", or "HIGH"
    """
    if empirical_thresholds:
        # Use empirical terciles from correlation analysis
        thresholds = empirical_thresholds['thresholds']
        
        if prod_deps <= thresholds['low_max']:
            risk_category = "LOW"
        elif prod_deps <= thresholds['medium_max']:
            risk_category = "MEDIUM"
        else:
            risk_category = "HIGH"
        
        # Adjust based on extrinsic ratio if significantly different from group average
        groups = empirical_thresholds['groups']
        expected_extrinsic = groups[risk_category.lower()]['avg_extrinsic']
        
        # If extrinsic ratio is 2× expected, bump up risk
        if extrinsic_ratio > expected_extrinsic * 2 and risk_category != "HIGH":
            if risk_category == "LOW":
                risk_category = "MEDIUM"
            else:
                risk_category = "HIGH"
        
        return risk_category
    
    else:
        # Fallback heuristics (based on typical npm ecosystem)
        if prod_deps >= 15 and extrinsic_ratio >= 55:
            return "HIGH"
        elif prod_deps >= 5 or extrinsic_ratio >= 45:
            return "MEDIUM"
        else:
            return "LOW"


def generate_recommendations(dep_info, bug_stats, risk_level, empirical_thresholds=None):
    """
    Generate actionable recommendations based on empirical findings
    
    Uses actual data from correlation analysis when available.
    """
    recommendations = []
    
    prod_deps = dep_info['production']
    extrinsic_ratio = bug_stats['ratios'].get('Extrinsic', 0)
    intrinsic_ratio = bug_stats['ratios'].get('Intrinsic', 0)
    total_bugs = bug_stats['total_bugs']
    
    # Dependency-related recommendations
    if empirical_thresholds:
        groups = empirical_thresholds['groups']
        
        # Determine which group package falls into
        thresholds = empirical_thresholds['thresholds']
        if prod_deps <= thresholds['low_max']:
            category = 'low'
            category_name = 'LOW'
        elif prod_deps <= thresholds['medium_max']:
            category = 'medium'
            category_name = 'MEDIUM'
        else:
            category = 'high'
            category_name = 'HIGH'
        
        avg_extrinsic = groups[category]['avg_extrinsic']
        
        recommendations.append(
            f"📊 Package is in {category_name} dependency complexity category "
            f"({groups[category]['dep_range']} production deps)"
        )
        
        recommendations.append(
            f"📊 Packages in this category average {avg_extrinsic:.1f}% extrinsic bugs "
            f"(yours: {extrinsic_ratio:.1f}%)"
        )
        
        # Comparison to category average
        if extrinsic_ratio > avg_extrinsic * 1.5:
            recommendations.append(
                f"⚠️  Your extrinsic ratio is {extrinsic_ratio / avg_extrinsic:.1f}× higher than category average"
            )
            recommendations.append(
                "💡 Focus on dependency version pinning and compatibility testing"
            )
        elif extrinsic_ratio < avg_extrinsic * 0.5:
            recommendations.append(
                f"✅ Your extrinsic ratio is below category average - good dependency isolation!"
            )
    
    # Specific dependency insights
    if prod_deps == 0:
        recommendations.append(
            "✅ Zero production dependencies - minimal external coupling"
        )
        if extrinsic_ratio > 5:
            recommendations.append(
                "💡 Extrinsic bugs likely due to environment/usage context rather than dependencies"
            )
    
    elif prod_deps >= 15:
        recommendations.append(
            f"⚠️  High production dependency count ({prod_deps}) increases maintenance surface"
        )
        recommendations.append(
            "💡 Consider dependency audit to identify unused or consolidatable packages"
        )
    
    # Extrinsic bug insights
    if extrinsic_ratio > 50:
        recommendations.append(
            f"⚠️  Majority of bugs ({extrinsic_ratio:.1f}%) are extrinsic"
        )
        recommendations.append(
            "💡 Strengthen integration tests and dependency version constraints"
        )
    elif extrinsic_ratio < 5:
        recommendations.append(
            f"✅ Very low extrinsic ratio ({extrinsic_ratio:.1f}%) - excellent dependency management"
        )
    
    # Intrinsic bug insights
    if intrinsic_ratio > 60:
        recommendations.append(
            f"⚠️  Majority of bugs ({intrinsic_ratio:.1f}%) are intrinsic (internal code issues)"
        )
        recommendations.append(
            "💡 Focus on code quality, testing coverage, and code review practices"
        )
    
    # Sample size warning
    if total_bugs < 20:
        recommendations.append(
            f"⚠️  Small sample size ({total_bugs} bugs) - statistical confidence is limited"
        )
    
    # Risk-specific recommendations
    if risk_level == "HIGH":
        recommendations.append(
            "🔴 HIGH RISK - Requires immediate attention to dependency management strategy"
        )
    elif risk_level == "MEDIUM":
        recommendations.append(
            "🟡 MEDIUM RISK - Monitor dependency updates and maintain good testing practices"
        )
    else:
        recommendations.append(
            "🟢 LOW RISK - Current dependency management appears effective"
        )
    
    return recommendations


def analyze_dependency_risk(package_name, classified_file="issues_with_classifications_21k.jsonl"):
    """
    Main analysis function for single package dependency risk assessment
    
    Args:
        package_name: npm package name (e.g., 'webpack', 'react')
        classified_file: path to merged classification file
    
    Returns:
        dict with complete analysis results
    """
    print(f"\n📦 DEPENDENCY RISK ANALYSIS")
    print("=" * 70)
    print(f"Package: {package_name}")
    print("=" * 70)
    
    # Load empirical thresholds if available
    print(f"\n🔍 Loading empirical thresholds from correlation analysis...")
    empirical_thresholds = load_empirical_thresholds()
    
    if empirical_thresholds:
        print(f"   ✓ Using empirical terciles from correlation study")
    else:
        print(f"   ⚠️  No empirical data found - using fallback heuristics")
        print(f"   💡 Run correlation_analyzer.py first for data-driven thresholds")
    
    # 1. Fetch package.json from npm
    print(f"\n1️⃣  Fetching package data from npm registry...")
    package_data = fetch_package_json(package_name)
    
    if not package_data:
        return {
            'error': f"Could not fetch package data for '{package_name}' from npm registry",
            'package': package_name
        }
    
    actual_name = package_data.get('name', package_name)
    version = package_data.get('version', 'unknown')
    description = package_data.get('description', 'No description')
    
    print(f"   ✓ Found: {actual_name} v{version}")
    print(f"   ⚠️  Note: Using LATEST version - may differ from historical bug context")
    
    # 2. Count dependencies
    print(f"\n2️⃣  Counting dependencies...")
    dep_info = count_dependencies(package_data)
    
    if not dep_info:
        return {
            'error': f"Could not parse dependencies for '{package_name}'",
            'package': package_name
        }
    
    print(f"   ✓ Total dependencies: {dep_info['total']}")
    print(f"     ├─ Production (risk-relevant): {dep_info['production']}")
    print(f"     │  ├─ Direct: {dep_info['direct']}")
    print(f"     │  ├─ Peer: {dep_info['peer']}")
    print(f"     │  └─ Optional: {dep_info['optional']}")
    print(f"     └─ Development (excluded): {dep_info['dev']}")
    
    # 3. Load and analyze bugs for this package
    print(f"\n3️⃣  Loading classified bugs for '{package_name}' from dataset...")
    bug_analysis = load_bugs_for_package(classified_file, package_name)
    
    if not bug_analysis:
        return {
            'error': f"No bugs found for package '{package_name}' in {classified_file}",
            'package': package_name,
            'dependencies': dep_info,
            'suggestion': f"Check if the package name matches the repo name in your dataset"
        }
    
    print(f"   ✓ Loaded {bug_analysis['total_bugs']} classified bugs")
    
    # 4. Calculate metrics
    print(f"\n4️⃣  Calculating risk metrics...")
    extrinsic_ratio = bug_analysis['ratios'].get('Extrinsic', 0)
    intrinsic_ratio = bug_analysis['ratios'].get('Intrinsic', 0)
    not_bug_ratio = bug_analysis['ratios'].get('Not  a Bug', 0)
    unknown_ratio = bug_analysis['ratios'].get('Unknown', 0)
    
    # Use PRODUCTION dependencies for risk assessment
    risk_level = assess_risk_level(
        dep_info['production'],
        extrinsic_ratio,
        empirical_thresholds
    )
    
    print(f"   ✓ Risk level: {risk_level}")
    
    # 5. Generate recommendations
    print(f"\n5️⃣  Generating recommendations...")
    recommendations = generate_recommendations(
        dep_info,
        bug_analysis,
        risk_level,
        empirical_thresholds
    )
    
    print(f"   ✓ Generated {len(recommendations)} recommendations")
    
    # 6. Compile full report
    report = {
        'package': actual_name,
        'version': version,
        'description': description,
        'dependencies': dep_info,
        'bugs': bug_analysis,
        'risk_assessment': {
            'level': risk_level,
            'dependency_count_total': dep_info['total'],
            'dependency_count_production': dep_info['production'],
            'dev_dependencies': dep_info['dev'],
            'extrinsic_ratio': extrinsic_ratio,
            'intrinsic_ratio': intrinsic_ratio,
            'not_bug_ratio': not_bug_ratio,
            'unknown_ratio': unknown_ratio,
            'used_empirical_thresholds': empirical_thresholds is not None
        },
        'recommendations': recommendations,
        'empirical_context': empirical_thresholds
    }
    
    return report


def format_report(report):
    """
    Format analysis report for display
    """
    if 'error' in report:
        output = [f"\n❌ Error: {report['error']}"]
        if 'suggestion' in report:
            output.append(f"\n💡 {report['suggestion']}")
        return "\n".join(output)
    
    output = []
    output.append("\n" + "=" * 70)
    output.append("📦 DEPENDENCY RISK ANALYSIS REPORT")
    output.append("=" * 70)
    
    # Package info
    output.append(f"\n📌 Package: {report['package']} v{report['version']}")
    desc = report['description'][:100] + "..." if len(report['description']) > 100 else report['description']
    output.append(f"   {desc}")
    
    # Temporal disclaimer
    output.append(f"\n⚠️  TEMPORAL NOTE:")
    output.append(f"   Dependencies reflect LATEST npm version (v{report['version']})")
    output.append(f"   Historical bugs may have been filed against different versions")
    output.append(f"   See temporal_validator.py for stability analysis")
    
    # Dependencies
    output.append(f"\n📊 Dependency Metrics:")
    output.append(f"   Production Dependencies (Risk-Relevant): {report['dependencies']['production']}")
    output.append(f"   ├─ Direct: {report['dependencies']['direct']}")
    output.append(f"   ├─ Peer: {report['dependencies']['peer']}")
    output.append(f"   └─ Optional: {report['dependencies']['optional']}")
    output.append(f"   ")
    output.append(f"   Development Dependencies (Excluded): {report['dependencies']['dev']}")
    output.append(f"   Total Dependencies: {report['dependencies']['total']}")
    
    # Bug distribution
    output.append(f"\n🐛 Bug Distribution (n={report['bugs']['total_bugs']}):")
    
    # Sort by count descending
    sorted_bugs = sorted(report['bugs']['counts'].items(), key=lambda x: -x[1])
    for bug_type, count in sorted_bugs:
        ratio = report['bugs']['ratios'][bug_type]
        bar_length = int(ratio / 2)  # Scale to max 50 chars
        bar = "█" * bar_length
        output.append(f"   {bug_type:15s}: {count:4d} ({ratio:5.1f}%) {bar}")
    
    # Risk assessment
    risk = report['risk_assessment']
    risk_emoji = {"LOW": "🟢", "MEDIUM": "🟡", "HIGH": "🔴"}
    
    output.append(f"\n{risk_emoji[risk['level']]} Risk Assessment: {risk['level']}")
    output.append(f"   Production Dependencies: {risk['dependency_count_production']}")
    output.append(f"   Extrinsic Ratio: {risk['extrinsic_ratio']:.1f}%")
    output.append(f"   Intrinsic Ratio: {risk['intrinsic_ratio']:.1f}%")
    
    if risk['used_empirical_thresholds']:
        output.append(f"   ✓ Risk level based on empirical terciles from 143-package study")
    else:
        output.append(f"   ⚠️  Risk level based on fallback heuristics (run correlation analysis for data-driven thresholds)")
    
    # Empirical context (if available)
    if report.get('empirical_context'):
        emp = report['empirical_context']
        output.append(f"\n📊 Ecosystem Context (from correlation study):")
        output.append(f"   {emp['interpretation']}")
        for risk_cat, data in emp['groups'].items():
            output.append(f"   {risk_cat.upper():8s}: {data['dep_range']:10s} (avg {data['avg_extrinsic']:.1f}% extrinsic)")
    
    # Recommendations
    output.append(f"\n💡 Recommendations:")
    for i, rec in enumerate(report['recommendations'], 1):
        # Wrap long recommendations
        if len(rec) > 65:
            lines = []
            current_line = ""
            words = rec.split()
            for word in words:
                if len(current_line) + len(word) + 1 <= 65:
                    current_line += word + " "
                else:
                    lines.append(current_line.strip())
                    current_line = "      " + word + " "
            lines.append(current_line.strip())
            output.append(f"   {i}. {lines[0]}")
            for line in lines[1:]:
                output.append(f"      {line}")
        else:
            output.append(f"   {i}. {rec}")
    
    output.append("\n" + "=" * 70)
    
    return "\n".join(output)


# For testing standalone
if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python dependency_analyzer.py <package_name> [classified_file]")
        print("\nExamples:")
        print("  python dependency_analyzer.py webpack")
        print("  python dependency_analyzer.py react issues_with_classifications_21k.jsonl")
        print("\nNote: Run correlation_analyzer.py first to generate empirical thresholds")
        sys.exit(1)
    
    package = sys.argv[1]
    classified_file = sys.argv[2] if len(sys.argv) > 2 else "issues_with_classifications_21k.jsonl"
    
    report = analyze_dependency_risk(package, classified_file)
    print(format_report(report))