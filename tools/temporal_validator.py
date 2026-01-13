"""
Temporal Stability Validator
Validates that dependency counts remain relatively stable over time
"""

import json
import requests
from datetime import datetime
from pathlib import Path
import random


def fetch_all_package_versions(package_name):
    """
    Fetch all versions and their publish times for a package
    
    Returns:
        list of {version, time, dependencies} sorted by time
    """
    url = f"https://registry.npmjs.org/{package_name}"
    
    try:
        response = requests.get(url, timeout=15)
        if response.status_code != 200:
            return None
        
        data = response.json()
        
        versions_data = []
        
        for version, version_info in data.get('versions', {}).items():
            publish_time = data.get('time', {}).get(version)
            
            if not publish_time:
                continue
            
            dependencies = version_info.get('dependencies', {})
            dev_dependencies = version_info.get('devDependencies', {})
            peer_dependencies = version_info.get('peerDependencies', {})
            optional_dependencies = version_info.get('optionalDependencies', {})
            
            production_count = len(dependencies) + len(peer_dependencies) + len(optional_dependencies)
            
            versions_data.append({
                'version': version,
                'published_at': publish_time,
                'production_deps': production_count,
                'total_deps': production_count + len(dev_dependencies)
            })
        
        # Sort by publish time
        versions_data.sort(key=lambda x: x['published_at'])
        
        return versions_data
        
    except Exception as e:
        print(f"Error fetching versions for {package_name}: {e}")
        return None


def find_version_at_time(versions_data, target_timestamp):
    """
    Find the most recent version published before target timestamp
    
    Args:
        versions_data: List from fetch_all_package_versions()
        target_timestamp: ISO timestamp string
    
    Returns:
        dict with version info at that time
    """
    if not versions_data:
        return None
    
    target_dt = datetime.fromisoformat(target_timestamp.replace('Z', '+00:00'))
    
    # Find latest version before target time
    matching_version = None
    
    for version_info in versions_data:
        version_dt = datetime.fromisoformat(version_info['published_at'].replace('Z', '+00:00'))
        
        if version_dt <= target_dt:
            matching_version = version_info
        else:
            break
    
    return matching_version


def validate_temporal_stability(classified_file, sample_size=50):
    """
    Validate that dependency counts are relatively stable over time
    
    Strategy:
    1. Sample N bugs from different time periods (2020-2025)
    2. For each bug, fetch historical dependency count at bug time
    3. Compare to current dependency count
    4. Report % difference
    
    Args:
        classified_file: Path to issues_with_classifications_21k.jsonl
        sample_size: Number of bugs to sample
    
    Returns:
        dict with validation results
    """
    print("\n" + "=" * 70)
    print("🕐 TEMPORAL STABILITY VALIDATION")
    print("=" * 70)
    
    print(f"\n1️⃣  Loading bugs from {classified_file}...")
    
    # Load all bugs
    all_bugs = []
    with open(classified_file, 'r', encoding='utf-8') as f:
        for line in f:
            if not line.strip():
                continue
            try:
                bug = json.loads(line)
                # Only bugs with timestamps
                if bug.get('created_at'):
                    all_bugs.append(bug)
            except json.JSONDecodeError:
                continue
    
    print(f"   ✓ Loaded {len(all_bugs)} bugs with timestamps")
    
    # Sample bugs across different years
    print(f"\n2️⃣  Sampling {sample_size} bugs across different time periods...")
    
    # Group by year
    bugs_by_year = {}
    for bug in all_bugs:
        year = bug['created_at'][:4]  # Extract year
        if year not in bugs_by_year:
            bugs_by_year[year] = []
        bugs_by_year[year].append(bug)
    
    print(f"   ✓ Bugs span years: {sorted(bugs_by_year.keys())}")
    
    # Sample evenly across years
    sampled_bugs = []
    for year, year_bugs in sorted(bugs_by_year.items()):
        n_sample = min(sample_size // len(bugs_by_year), len(year_bugs))
        sampled_bugs.extend(random.sample(year_bugs, n_sample))
    
    # Ensure we have sample_size bugs
    if len(sampled_bugs) < sample_size:
        remaining = sample_size - len(sampled_bugs)
        sampled_bugs.extend(random.sample(all_bugs, min(remaining, len(all_bugs))))
    
    sampled_bugs = sampled_bugs[:sample_size]
    
    print(f"   ✓ Sampled {len(sampled_bugs)} bugs")
    
    # Get unique packages from sample
    packages_to_check = {}
    for bug in sampled_bugs:
        repo = bug.get('repo', '')
        if '/' in repo:
            package_name = repo.split('/')[-1]
        else:
            package_name = repo
        
        if package_name not in packages_to_check:
            packages_to_check[package_name] = []
        
        packages_to_check[package_name].append({
            'bug_number': bug.get('number'),
            'created_at': bug.get('created_at')
        })
    
    print(f"   ✓ Unique packages in sample: {len(packages_to_check)}")
    
    # Validate each package
    print(f"\n3️⃣  Fetching historical dependency data...")
    
    validation_results = []
    failed_packages = []
    
    for i, (package_name, bugs) in enumerate(packages_to_check.items(), 1):
        print(f"   [{i}/{len(packages_to_check)}] {package_name}...", end=" ", flush=True)
        
        # Fetch all versions
        versions = fetch_all_package_versions(package_name)
        
        if not versions:
            print("❌ Failed")
            failed_packages.append(package_name)
            continue
        
        # Get latest version
        latest_version = versions[-1]
        
        # For each bug, find historical version
        for bug in bugs:
            historical_version = find_version_at_time(versions, bug['created_at'])
            
            if historical_version:
                diff_prod = latest_version['production_deps'] - historical_version['production_deps']
                pct_change_prod = (diff_prod / historical_version['production_deps'] * 100) if historical_version['production_deps'] > 0 else 0
                
                validation_results.append({
                    'package': package_name,
                    'bug_number': bug['bug_number'],
                    'bug_date': bug['created_at'][:10],
                    'historical_version': historical_version['version'],
                    'historical_prod_deps': historical_version['production_deps'],
                    'latest_version': latest_version['version'],
                    'latest_prod_deps': latest_version['production_deps'],
                    'diff_prod_deps': diff_prod,
                    'pct_change_prod': round(pct_change_prod, 2)
                })
        
        print(f"✓")
    
    print(f"\n   ✓ Validated {len(validation_results)} bug-package pairs")
    if failed_packages:
        print(f"   ⚠️  Failed: {len(failed_packages)} packages")
    
    # Calculate statistics
    print(f"\n4️⃣  Calculating temporal stability statistics...")
    
    if not validation_results:
        return {'error': 'No validation results'}
    
    pct_changes = [r['pct_change_prod'] for r in validation_results]
    abs_pct_changes = [abs(x) for x in pct_changes]
    
    import statistics
    
    stats = {
        'sample_size': len(validation_results),
        'packages_checked': len(packages_to_check) - len(failed_packages),
        'failed_packages': len(failed_packages),
        'pct_change_stats': {
            'mean': round(statistics.mean(pct_changes), 2),
            'median': round(statistics.median(pct_changes), 2),
            'std_dev': round(statistics.stdev(pct_changes), 2) if len(pct_changes) > 1 else 0,
            'abs_mean': round(statistics.mean(abs_pct_changes), 2),
            'min': round(min(pct_changes), 2),
            'max': round(max(pct_changes), 2)
        },
        'stability_assessment': None
    }
    
    # Assess stability
    abs_mean = stats['pct_change_stats']['abs_mean']
    if abs_mean < 15:
        assessment = "HIGH STABILITY - Dependency counts changed by <15% on average"
    elif abs_mean < 30:
        assessment = "MODERATE STABILITY - Dependency counts changed by 15-30% on average"
    else:
        assessment = "LOW STABILITY - Dependency counts changed by >30% on average"
    
    stats['stability_assessment'] = assessment
    stats['details'] = validation_results
    
    print(f"   ✓ Stability assessment: {assessment}")
    
    return stats


def format_validation_report(stats):
    """Format validation results for display"""
    
    if 'error' in stats:
        return f"❌ Error: {stats['error']}"
    
    output = []
    output.append("\n" + "=" * 70)
    output.append("📊 TEMPORAL STABILITY VALIDATION RESULTS")
    output.append("=" * 70)
    
    output.append(f"\n📦 Sample:")
    output.append(f"   Bug-package pairs validated: {stats['sample_size']}")
    output.append(f"   Unique packages: {stats['packages_checked']}")
    output.append(f"   Failed to fetch: {stats['failed_packages']}")
    
    pct = stats['pct_change_stats']
    output.append(f"\n📈 Production Dependency Change (Historical vs Latest):")
    output.append(f"   Mean change: {pct['mean']:+.1f}%")
    output.append(f"   Median change: {pct['median']:+.1f}%")
    output.append(f"   Std deviation: {pct['std_dev']:.1f}%")
    output.append(f"   Mean absolute change: {pct['abs_mean']:.1f}%")
    output.append(f"   Range: {pct['min']:.1f}% to {pct['max']:.1f}%")
    
    output.append(f"\n✅ Assessment: {stats['stability_assessment']}")
    
    # Show some examples
    output.append(f"\n📋 Sample Details (first 10):")
    for i, detail in enumerate(stats['details'][:10], 1):
        output.append(f"   {i}. {detail['package']} (bug from {detail['bug_date']})")
        output.append(f"      Historical: {detail['historical_prod_deps']} deps ({detail['historical_version']})")
        output.append(f"      Latest: {detail['latest_prod_deps']} deps ({detail['latest_version']})")
        output.append(f"      Change: {detail['pct_change_prod']:+.1f}%")
    
    output.append("\n" + "=" * 70)
    
    return "\n".join(output)


# For standalone testing
if __name__ == "__main__":
    import sys
    
    classified_file = sys.argv[1] if len(sys.argv) > 1 else "issues_with_classifications_21k.jsonl"
    sample_size = int(sys.argv[2]) if len(sys.argv) > 2 else 50
    
    if not Path(classified_file).exists():
        print(f"❌ Error: File not found: {classified_file}")
        sys.exit(1)
    
    # Run validation
    stats = validate_temporal_stability(classified_file, sample_size)
    
    # Display results
    print(format_validation_report(stats))
    
    # Save results
    output_file = "temporal_validation_results.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(stats, f, indent=2, ensure_ascii=False)
    
    print(f"\n💾 Full results saved to: {output_file}")