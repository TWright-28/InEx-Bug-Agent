"""
Correlation Analysis for RQ7.1
Analyzes correlation between dependency count and extrinsic bug ratio across all packages
"""

import json
import requests
from pathlib import Path
from collections import defaultdict
import time


def fetch_package_json(package_name):
    url = f"https://registry.npmjs.org/{package_name}/latest"
    
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            return response.json()
        return None
    except Exception:
        return None


def count_dependencies(package_data):
    """
    Count dependencies with focus on production (runtime) dependencies
    
    Returns:
        dict with dependency counts and risk-relevant metrics
    """
    if not package_data:
        return None
    
    dependencies = package_data.get('dependencies', {})
    dev_dependencies = package_data.get('devDependencies', {})
    peer_dependencies = package_data.get('peerDependencies', {})
    optional_dependencies = package_data.get('optionalDependencies', {})
    
    # Production dependencies = runtime exposure
    production = len(dependencies) + len(peer_dependencies) + len(optional_dependencies)
    
    return {
        'direct': len(dependencies),
        'dev': len(dev_dependencies),
        'peer': len(peer_dependencies),
        'optional': len(optional_dependencies),
        'total': len(dependencies) + len(dev_dependencies) + len(peer_dependencies) + len(optional_dependencies),
        'production': production,  # RISK-RELEVANT metric
        'dependency_names': {
            'dependencies': list(dependencies.keys()),
            'devDependencies': list(dev_dependencies.keys()),
            'peerDependencies': list(peer_dependencies.keys()),
            'optionalDependencies': list(optional_dependencies.keys())
        }
    }


def extract_all_packages(classified_file):
    """
    Extract all unique packages from the 21K dataset
    
    Returns:
        dict: {package_name: [list of bugs]}
    """
    print(f"\n📂 Extracting packages from {classified_file}...")
    
    packages = defaultdict(list)
    
    with open(classified_file, 'r', encoding='utf-8') as f:
        for line in f:
            if not line.strip():
                continue
            
            try:
                issue = json.loads(line)
                
                # Extract package name from repo field
                repo = issue.get('repo', '')
                
                if '/' in repo:
                    package_name = repo.split('/')[-1]
                else:
                    package_name = repo
                
                if package_name:
                    packages[package_name].append(issue)
                    
            except json.JSONDecodeError:
                continue
    
    print(f"   ✓ Found {len(packages)} unique packages")
    
    # Show distribution
    bug_counts = [len(bugs) for bugs in packages.values()]
    print(f"   ✓ Total bugs: {sum(bug_counts)}")
    print(f"   ✓ Average bugs per package: {sum(bug_counts) / len(packages):.1f}")
    print(f"   ✓ Min bugs: {min(bug_counts)}")
    print(f"   ✓ Max bugs: {max(bug_counts)}")
    
    return dict(packages)


def calculate_bug_ratios(bugs):
    """Calculate intrinsic/extrinsic ratios for a list of bugs"""
    counts = defaultdict(int)
    
    for bug in bugs:
        classification = bug.get('final_classification', 'Unknown')
        counts[classification] += 1
    
    total = len(bugs)
    
    return {
        'total': total,
        'intrinsic_count': counts['Intrinsic'],
        'extrinsic_count': counts['Extrinsic'],
        'not_bug_count': counts['Not  a Bug'],
        'unknown_count': counts['Unknown'],
        'intrinsic_ratio': (counts['Intrinsic'] / total * 100) if total > 0 else 0,
        'extrinsic_ratio': (counts['Extrinsic'] / total * 100) if total > 0 else 0,
        'not_bug_ratio': (counts['Not  a Bug'] / total * 100) if total > 0 else 0,
        'unknown_ratio': (counts['Unknown'] / total * 100) if total > 0 else 0
    }


def analyze_all_packages(classified_file, min_bugs=10, max_packages=None, output_file="correlation_data.json"):
    """
    Main correlation analysis across all packages (Option B for RQ7.1)
    
    Args:
        classified_file: Path to issues_with_classifications_21k.jsonl
        min_bugs: Minimum bugs required for a package to be included
        max_packages: Maximum number of packages to analyze (None = all)
        output_file: Where to save the correlation data
    
    Returns:
        dict with correlation analysis results
    """
    print("\n" + "=" * 70)
    print("🔬 CORRELATION ANALYSIS: DEPENDENCIES vs EXTRINSIC BUGS (RQ7.1)")
    print("=" * 70)
    
    # 1. Extract all packages from dataset
    all_packages = extract_all_packages(classified_file)
    
    # 2. Filter packages with minimum bug count
    print(f"\n📊 Filtering packages (min {min_bugs} bugs)...")
    filtered_packages = {
        pkg: bugs for pkg, bugs in all_packages.items() 
        if len(bugs) >= min_bugs
    }
    print(f"   ✓ {len(filtered_packages)} packages meet criteria (≥{min_bugs} bugs)")
    
    # 3. Limit number of packages if specified
    if max_packages and len(filtered_packages) > max_packages:
        print(f"\n⚠️  Limiting to {max_packages} packages (for faster analysis)")
        # Sort by bug count descending, take top N
        sorted_packages = sorted(filtered_packages.items(), key=lambda x: len(x[1]), reverse=True)
        filtered_packages = dict(sorted_packages[:max_packages])
    
    # 4. Fetch dependency data for each package
    print(f"\n🌐 Fetching dependency data from npm registry...")
    print(f"   (This may take a while - {len(filtered_packages)} packages)")
    
    analysis_data = []
    failed_packages = []
    
    for i, (package_name, bugs) in enumerate(filtered_packages.items(), 1):
        print(f"   [{i}/{len(filtered_packages)}] {package_name}...", end=" ", flush=True)
        
        # Fetch package.json
        package_data = fetch_package_json(package_name)
        
        if not package_data:
            print("❌ Failed to fetch")
            failed_packages.append(package_name)
            continue
        
        # Count dependencies
        dep_info = count_dependencies(package_data)
        
        if not dep_info:
            print("❌ No dependency data")
            failed_packages.append(package_name)
            continue
        
        # Calculate bug ratios
        bug_stats = calculate_bug_ratios(bugs)
        
        # Compile data point
        data_point = {
            'package': package_name,
            'version': package_data.get('version', 'unknown'),
            'description': package_data.get('description', '')[:100],
            'dependencies': dep_info,
            'bugs': bug_stats
        }
        
        analysis_data.append(data_point)
        
        print(f"✓ (deps: {dep_info['total']}, extrinsic: {bug_stats['extrinsic_ratio']:.1f}%)")
        
        # Rate limiting - be nice to npm
        if i % 10 == 0:
            time.sleep(1)
    
    print(f"\n   ✓ Successfully analyzed {len(analysis_data)} packages")
    if failed_packages:
        print(f"   ⚠️  Failed to fetch {len(failed_packages)} packages")
    
    # 5. Calculate correlation statistics
    print(f"\n📈 Calculating correlation statistics...")
    
    correlation_results = calculate_correlation(analysis_data)
    
    # 6. Save data to file
    print(f"\n💾 Saving correlation data to {output_file}...")
    
    empirical_thresholds = calculate_empirical_thresholds(analysis_data)


    full_results = {
        'metadata': {
            'total_packages_analyzed': len(analysis_data),
            'min_bugs_threshold': min_bugs,
            'failed_packages': failed_packages
        },
        'correlation': correlation_results,
        'empirical_thresholds': empirical_thresholds,
        'data_points': analysis_data
    }
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(full_results, f, indent=2, ensure_ascii=False)
    
    print(f"   ✓ Data saved")
    
    return full_results


def calculate_correlation(data_points):
    """
    Calculate correlation coefficient and regression statistics
    
    Args:
        data_points: List of package analysis results
    
    Returns:
        dict with correlation statistics
    """
    if not data_points:
        return None
    
    # Extract x (dependency count) and y (extrinsic ratio)
    x_values = [dp['dependencies']['production'] for dp in data_points]
    y_values = [dp['bugs']['extrinsic_ratio'] for dp in data_points]
    
    n = len(x_values)
    
    # Calculate means
    x_mean = sum(x_values) / n
    y_mean = sum(y_values) / n
    
    # Calculate Pearson correlation coefficient
    numerator = sum((x_values[i] - x_mean) * (y_values[i] - y_mean) for i in range(n))
    denominator_x = sum((x - x_mean) ** 2 for x in x_values)
    denominator_y = sum((y - y_mean) ** 2 for y in y_values)
    
    if denominator_x == 0 or denominator_y == 0:
        r = 0
    else:
        r = numerator / (denominator_x * denominator_y) ** 0.5
    
    # Simple linear regression: y = mx + b
    if denominator_x != 0:
        m = numerator / denominator_x  # Slope
        b = y_mean - m * x_mean  # Intercept
    else:
        m = 0
        b = y_mean
    
    # R-squared
    r_squared = r ** 2
    
    prod_deps = sorted([dp['dependencies']['production'] for dp in data_points])
    median_deps = prod_deps[len(prod_deps) // 2]

    high_dep_packages = [dp for dp in data_points if dp['dependencies']['production'] >= median_deps]
    low_dep_packages = [dp for dp in data_points if dp['dependencies']['production'] < median_deps]
    
    high_dep_extrinsic_avg = (
        sum(dp['bugs']['extrinsic_ratio'] for dp in high_dep_packages) / len(high_dep_packages)
        if high_dep_packages else 0
    )
    
    low_dep_extrinsic_avg = (
        sum(dp['bugs']['extrinsic_ratio'] for dp in low_dep_packages) / len(low_dep_packages)
        if low_dep_packages else 0
    )
    
    return {
        'pearson_r': round(r, 4),
        'r_squared': round(r_squared, 4),
        'regression': {
            'slope': round(m, 4),
            'intercept': round(b, 4),
            'equation': f"extrinsic_ratio = {m:.4f} * dep_count + {b:.4f}"
        },
        'threshold_analysis': {
            'threshold': median_deps,
            'high_dep_packages': len(high_dep_packages),
            'low_dep_packages': len(low_dep_packages),
            'high_dep_avg_extrinsic': round(high_dep_extrinsic_avg, 2),
            'low_dep_avg_extrinsic': round(low_dep_extrinsic_avg, 2),
            'difference': round(high_dep_extrinsic_avg - low_dep_extrinsic_avg, 2)
        },
        'descriptive_stats': {
            'n': n,
            'dep_count_mean': round(x_mean, 2),
            'dep_count_min': min(x_values),
            'dep_count_max': max(x_values),
            'extrinsic_ratio_mean': round(y_mean, 2),
            'extrinsic_ratio_min': round(min(y_values), 2),
            'extrinsic_ratio_max': round(max(y_values), 2)
        }
    }


def format_correlation_report(results):
    """Format correlation analysis results for display"""
    
    if not results or 'correlation' not in results:
        return "❌ No correlation data available"
    
    corr = results['correlation']
    meta = results['metadata']
    
    output = []
    output.append("\n" + "=" * 70)
    output.append("📊 CORRELATION ANALYSIS RESULTS (RQ7.1)")
    output.append("=" * 70)
    
    # Sample info
    output.append(f"\n📦 Sample:")
    output.append(f"   Packages analyzed: {meta['total_packages_analyzed']}")
    output.append(f"   Minimum bugs per package: {meta['min_bugs_threshold']}")
    
    # Correlation coefficient
    output.append(f"\n📈 Correlation Coefficient:")
    output.append(f"   Pearson's r: {corr['pearson_r']}")
    output.append(f"   R-squared: {corr['r_squared']}")
    
    # Interpret correlation strength
    r_abs = abs(corr['pearson_r'])
    if r_abs < 0.3:
        strength = "weak"
    elif r_abs < 0.7:
        strength = "moderate"
    else:
        strength = "strong"
    
    direction = "positive" if corr['pearson_r'] > 0 else "negative"
    output.append(f"   Interpretation: {strength.upper()} {direction} correlation")
    
    # Regression equation
    output.append(f"\n📐 Linear Regression:")
    output.append(f"   {corr['regression']['equation']}")
    output.append(f"   ")
    output.append(f"   Interpretation:")
    slope = corr['regression']['slope']
    output.append(f"   - Each additional 10 dependencies → {slope * 10:+.2f}% change in extrinsic ratio")
    
    # Threshold analysis
    thresh = corr['threshold_analysis']
    median_threshold = None
    if 'empirical_thresholds' in results:
        median_threshold = results['empirical_thresholds']['thresholds']['medium_max'] + 1
    else:
        # Fallback to calculating median
        prod_deps = sorted([dp['dependencies']['production'] for dp in results['data_points']])
        median_threshold = prod_deps[len(prod_deps) // 2]

    output.append(f"\n🔍 Threshold Analysis (Median Split: {median_threshold}):")
    output.append(f"   Packages with ≥{median_threshold} deps: {thresh['high_dep_packages']}")
    output.append(f"   Packages with <{median_threshold} deps: {thresh['low_dep_packages']}")
    output.append(f"   ")
    output.append(f"   Average extrinsic ratio:")
    output.append(f"   - High dependency (≥{median_threshold}): {thresh['high_dep_avg_extrinsic']:.1f}%")
    output.append(f"   - Low dependency (<{median_threshold}):  {thresh['low_dep_avg_extrinsic']:.1f}%")
    output.append(f"   - Difference: {thresh['difference']:+.1f}%")
    output.append(f"   ")

    # Empirical terciles
    if 'empirical_thresholds' in results:
        emp = results['empirical_thresholds']
        output.append(f"\n📊 Empirical Risk Categories (Terciles):")
        output.append(f"   {emp['interpretation']}")
        output.append(f"   ")
        for risk_level, data in emp['groups'].items():
            output.append(f"   {risk_level.upper():8s}: {data['dep_range']:10s} ({data['count']:3d} packages, {data['avg_extrinsic']:.1f}% extrinsic avg)")

    # Descriptive stats
    desc = corr['descriptive_stats']
    output.append(f"\n📊 Descriptive Statistics:")
    output.append(f"   Production Dependency Count:")
    output.append(f"   - Mean: {desc['dep_count_mean']:.1f}")
    output.append(f"   - Range: {desc['dep_count_min']} - {desc['dep_count_max']}")
    output.append(f"   ")
    output.append(f"   Extrinsic Ratio:")
    output.append(f"   - Mean: {desc['extrinsic_ratio_mean']:.1f}%")
    output.append(f"   - Range: {desc['extrinsic_ratio_min']:.1f}% - {desc['extrinsic_ratio_max']:.1f}%")
    
    # Top packages by dependency count
    output.append(f"\n🔝 Top 5 Packages by Dependency Count:")
    sorted_data = sorted(results['data_points'], key=lambda x: x['dependencies']['total'], reverse=True)
    for i, dp in enumerate(sorted_data[:5], 1):
        output.append(f"   {i}. {dp['package']}: {dp['dependencies']['total']} deps, {dp['bugs']['extrinsic_ratio']:.1f}% extrinsic")
    
    # Top packages by extrinsic ratio
    output.append(f"\n🔝 Top 5 Packages by Extrinsic Ratio:")
    sorted_by_extrinsic = sorted(results['data_points'], key=lambda x: x['bugs']['extrinsic_ratio'], reverse=True)
    for i, dp in enumerate(sorted_by_extrinsic[:5], 1):
        output.append(f"   {i}. {dp['package']}: {dp['bugs']['extrinsic_ratio']:.1f}% extrinsic, {dp['dependencies']['total']} deps")
    
    output.append("\n" + "=" * 70)
    output.append("\n💾 Full data saved to: correlation_data.json")
    output.append("📊 Use this data for scatter plots and further statistical analysis")
    output.append("=" * 70)
    
    return "\n".join(output)


def calculate_empirical_thresholds(data_points):
    """
    Calculate data-driven thresholds using terciles (33rd, 66th percentiles)
    
    Args:
        data_points: List of package analysis results
    
    Returns:
        dict with empirical thresholds
    """
    if not data_points:
        return None
    
    # Extract production dependency counts
    prod_deps = sorted([dp['dependencies']['production'] for dp in data_points])
    n = len(prod_deps)
    
    # Calculate terciles (33rd and 66th percentiles)
    p33_index = int(n * 0.33)
    p66_index = int(n * 0.66)
    
    low_threshold = prod_deps[p33_index]
    high_threshold = prod_deps[p66_index]
    
    # Group packages by risk category
    low_risk = [dp for dp in data_points if dp['dependencies']['production'] < low_threshold]
    medium_risk = [dp for dp in data_points if low_threshold <= dp['dependencies']['production'] < high_threshold]
    high_risk = [dp for dp in data_points if dp['dependencies']['production'] >= high_threshold]
    
    # Calculate average extrinsic ratio for each group
    low_avg_extrinsic = (
        sum(dp['bugs']['extrinsic_ratio'] for dp in low_risk) / len(low_risk)
        if low_risk else 0
    )
    
    medium_avg_extrinsic = (
        sum(dp['bugs']['extrinsic_ratio'] for dp in medium_risk) / len(medium_risk)
        if medium_risk else 0
    )
    
    high_avg_extrinsic = (
        sum(dp['bugs']['extrinsic_ratio'] for dp in high_risk) / len(high_risk)
        if high_risk else 0
    )
    
    return {
        'thresholds': {
            'low_max': low_threshold - 1,
            'medium_min': low_threshold,
            'medium_max': high_threshold - 1,
            'high_min': high_threshold
        },
        'groups': {
            'low': {
                'count': len(low_risk),
                'dep_range': f"0-{low_threshold-1}",
                'avg_extrinsic': round(low_avg_extrinsic, 2)
            },
            'medium': {
                'count': len(medium_risk),
                'dep_range': f"{low_threshold}-{high_threshold-1}",
                'avg_extrinsic': round(medium_avg_extrinsic, 2)
            },
            'high': {
                'count': len(high_risk),
                'dep_range': f"{high_threshold}+",
                'avg_extrinsic': round(high_avg_extrinsic, 2)
            }
        },
        'interpretation': f"LOW: <{low_threshold} deps, MEDIUM: {low_threshold}-{high_threshold-1} deps, HIGH: ≥{high_threshold} deps"
    }


# For testing standalone
if __name__ == "__main__":
    import sys
    
    classified_file = sys.argv[1] if len(sys.argv) > 1 else "issues_with_classifications_21k.jsonl"
    
    if not Path(classified_file).exists():
        print(f"❌ Error: File not found: {classified_file}")
        sys.exit(1)
    
    # Run correlation analysis
    # Start with max 50 packages for testing, remove limit for full analysis
    results = analyze_all_packages(
        classified_file,
        min_bugs=10,  # Only include packages with 10+ bugs
        max_packages=None,  # Limit to 50 packages for faster testing (remove for full analysis)
        output_file="correlation_data_full.json"
    )
    
    if results and 'data_points' in results:
        empirical = calculate_empirical_thresholds(results['data_points'])
        results['empirical_thresholds'] = empirical
        
        # Save updated results
        with open("correlation_data_full.json", 'w') as f:
            json.dump(results, f, indent=2)


    # Display results
    print(format_correlation_report(results))