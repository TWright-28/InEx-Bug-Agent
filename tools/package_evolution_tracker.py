import json
import requests
from pathlib import Path
from datetime import datetime
from collections import defaultdict


def fetch_all_package_versions(package_name):
    print(f"\n Fetching version history for {package_name}...")
    
    url = f"https://registry.npmjs.org/{package_name}"
    
    try:
        response = requests.get(url, timeout=15)
        if response.status_code != 200:
            print(f"    Failed: HTTP {response.status_code}")
            return None
        
        data = response.json()
        print(f"    Found {len(data.get('versions', {}))} versions")
        return data
        
    except Exception as e:
        print(f"    Error: {e}")
        return None


def build_version_timeline(package_data):
    if not package_data or 'versions' not in package_data:
        return None
    
    print(f"\n Building version timeline...")
    
    timeline = []
    
    for version, version_info in package_data['versions'].items():
        publish_time_str = package_data.get('time', {}).get(version)
        
        if not publish_time_str:
            continue
        
        try:
            publish_dt = datetime.fromisoformat(publish_time_str.replace('Z', '+00:00'))
        except Exception:
            continue
        
        dependencies = version_info.get('dependencies', {})
        peer_dependencies = version_info.get('peerDependencies', {})
        optional_dependencies = version_info.get('optionalDependencies', {})
        
        production_deps = len(dependencies) + len(peer_dependencies) + len(optional_dependencies)

        is_major = version.split('.')[1] == '0' and version.split('.')[2] == '0'
        
        timeline.append({
            'version': version,
            'published_at': publish_dt,
            'published_str': publish_time_str[:10],  # YYYY-MM-DD
            'production_deps': production_deps,
            'is_major': is_major
        })
    
    timeline.sort(key=lambda x: x['published_at'])
    
    print(f"    Timeline built: {len(timeline)} versions from {timeline[0]['published_str']} to {timeline[-1]['published_str']}")
    
    return timeline


def load_package_bugs(classified_file, package_name):
    print(f"\n Loading bugs for {package_name}...")
    
    bugs = []
    
    with open(classified_file, 'r', encoding='utf-8') as f:
        for line in f:
            if not line.strip():
                continue
            
            try:
                bug = json.loads(line)
                
                repo = bug.get('repo', '')
                if '/' in repo:
                    pkg = repo.split('/')[-1]
                else:
                    pkg = repo
                
                if pkg.lower() == package_name.lower() and bug.get('created_at'):
                    bugs.append(bug)
                    
            except json.JSONDecodeError:
                continue
    
    if not bugs:
        print(f"    No bugs found for {package_name}")
        return None
    
    print(f"    Loaded {len(bugs)} bugs")
    
    for bug in bugs:
        try:
            bug['created_dt'] = datetime.fromisoformat(bug['created_at'].replace('Z', '+00:00'))
        except Exception:
            bug['created_dt'] = None
    
    bugs = [b for b in bugs if b['created_dt'] is not None]
    
    print(f"    {len(bugs)} bugs have valid timestamps")
    
    return bugs


def assign_bugs_to_versions(bugs, version_timeline):
    print(f"\n Assigning bugs to versions...")
    
    bugs_by_version = defaultdict(list)
    unassigned = 0
    
    for bug in bugs:
        bug_dt = bug['created_dt']
        
        assigned_version = None
        
        for version_info in version_timeline:
            if version_info['published_at'] <= bug_dt:
                assigned_version = version_info['version']
            else:
                break
        
        if assigned_version:
            bugs_by_version[assigned_version].append(bug)
        else:
            unassigned += 1
    
    print(f"    Assigned {len(bugs) - unassigned} bugs to {len(bugs_by_version)} versions")
    if unassigned > 0:
        print(f"     {unassigned} bugs filed before first version (skipped)")
    
    return dict(bugs_by_version)


def analyze_version_composition(bugs_by_version, version_timeline):
    print(f"\n Analyzing bug composition per version...")
    
    results = []
    
    version_metadata = {v['version']: v for v in version_timeline}
    
    for version, bugs in bugs_by_version.items():
        metadata = version_metadata.get(version, {})
        
        counts = defaultdict(int)
        for bug in bugs:
            classification = bug.get('final_classification', 'Unknown')
            counts[classification] += 1
        
        total = len(bugs)
        
        intrinsic_pct = (counts['Intrinsic'] / total * 100) if total > 0 else 0
        extrinsic_pct = (counts['Extrinsic'] / total * 100) if total > 0 else 0
        not_bug_pct = (counts['Not  a Bug'] / total * 100) if total > 0 else 0
        unknown_pct = (counts['Unknown'] / total * 100) if total > 0 else 0
        
        results.append({
            'version': version,
            'published_at': metadata.get('published_str', 'Unknown'),
            'production_deps': metadata.get('production_deps', 0),
            'is_major': metadata.get('is_major', False),
            'total_bugs': total,
            'counts': {
                'intrinsic': counts['Intrinsic'],
                'extrinsic': counts['Extrinsic'],
                'not_bug': counts['Not  a Bug'],
                'unknown': counts['Unknown']
            },
            'percentages': {
                'intrinsic': round(intrinsic_pct, 1),
                'extrinsic': round(extrinsic_pct, 1),
                'not_bug': round(not_bug_pct, 1),
                'unknown': round(unknown_pct, 1)
            }
        })
    
    results.sort(key=lambda x: x['published_at'])
    
    print(f"    Analysis complete for {len(results)} versions")
    
    return results


def format_evolution_report(package_name, results, version_timeline):

    if not results:
        return f" No data to display for {package_name}"
    
    output = []
    output.append("\n" + "=" * 70)
    output.append(f" {package_name.upper()} BUG EVOLUTION BY VERSION")
    output.append("=" * 70)
    
    total_bugs = sum(r['total_bugs'] for r in results)
    first = results[0]
    last = results[-1]
    
    output.append(f"\n Overview:")
    output.append(f"   Total bugs analyzed: {total_bugs}")
    output.append(f"   Versions tracked: {len(results)}")
    output.append(f"   Date range: {first['published_at']} to {last['published_at']}")
    output.append(f"   Dependency growth: {first['production_deps']} → {last['production_deps']} production deps")
    
    output.append(f"\n" + "─" * 70)
    
    for r in results:
        header = f"v{r['version']} (Released: {r['published_at']}, deps: {r['production_deps']})"
        if r['is_major']:
            header += "  MAJOR"
        
        output.append(f"\n{header}")
        output.append(f"  Bugs: {r['total_bugs']}")
        
        counts = r['counts']
        pcts = r['percentages']
        
        output.append(f"  - Intrinsic: {counts['intrinsic']:3d} ({pcts['intrinsic']:5.1f}%)")
        output.append(f"  - Extrinsic: {counts['extrinsic']:3d} ({pcts['extrinsic']:5.1f}%)")
        output.append(f"  - Not a Bug: {counts['not_bug']:3d} ({pcts['not_bug']:5.1f}%)")
        output.append(f"  - Unknown:   {counts['unknown']:3d} ({pcts['unknown']:5.1f}%)")
    
    output.append(f"\n" + "─" * 70)
    
    output.append(f"\n TRENDS:")
    output.append(f"   Extrinsic: {first['percentages']['extrinsic']:.1f}% → {last['percentages']['extrinsic']:.1f}% ({last['percentages']['extrinsic'] - first['percentages']['extrinsic']:+.1f}%)")
    output.append(f"   Intrinsic: {first['percentages']['intrinsic']:.1f}% → {last['percentages']['intrinsic']:.1f}% ({last['percentages']['intrinsic'] - first['percentages']['intrinsic']:+.1f}%)")
    
    versions_by_extrinsic = sorted(results, key=lambda x: x['percentages']['extrinsic'], reverse=True)
    versions_by_bugs = sorted(results, key=lambda x: x['total_bugs'], reverse=True)
    
    output.append(f"\n Notable Versions:")
    output.append(f"   Highest extrinsic ratio: v{versions_by_extrinsic[0]['version']} ({versions_by_extrinsic[0]['percentages']['extrinsic']:.1f}%)")
    output.append(f"   Most bugs filed: v{versions_by_bugs[0]['version']} ({versions_by_bugs[0]['total_bugs']} bugs)")
    
    output.append("\n" + "=" * 70)
    
    return "\n".join(output)


def track_package_evolution(package_name, classified_file="issues_with_classifications_21k.jsonl", output_file=None):

    print(f"\n Starting evolution tracking for {package_name}")
    print("=" * 70)
    
    package_data = fetch_all_package_versions(package_name)
    if not package_data:
        return {'error': 'Failed to fetch package data'}
    
    version_timeline = build_version_timeline(package_data)
    if not version_timeline:
        return {'error': 'Failed to build version timeline'}
    
    bugs = load_package_bugs(classified_file, package_name)
    if not bugs:
        return {'error': f'No bugs found for {package_name}'}
    
    bugs_by_version = assign_bugs_to_versions(bugs, version_timeline)
    if not bugs_by_version:
        return {'error': 'Failed to assign bugs to versions'}
    
    results = analyze_version_composition(bugs_by_version, version_timeline)
    
    final_results = {
        'package': package_name,
        'total_bugs': len(bugs),
        'versions_tracked': len(results),
        'version_timeline': version_timeline,
        'analysis_results': results
    }
    
    if output_file:
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(final_results, f, indent=2, ensure_ascii=False, default=str)
        print(f"\n Results saved to: {output_file}")
    
    return final_results


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python package_evolution_tracker.py <package_name> [classified_file]")
        print("\nExamples:")
        print("  python package_evolution_tracker.py axios")
        print("  python package_evolution_tracker.py webpack issues_with_classifications_21k.jsonl")
        sys.exit(1)
    
    package = sys.argv[1]
    classified_file = sys.argv[2] if len(sys.argv) > 2 else "issues_with_classifications_21k.jsonl"
    
    if not Path(classified_file).exists():
        print(f" Error: File not found: {classified_file}")
        sys.exit(1)
    
    results = track_package_evolution(
        package,
        classified_file,
        output_file=f"{package}_evolution.json"
    )
    
    if 'error' in results:
        print(f"\n Error: {results['error']}")
        sys.exit(1)
    
    print(format_evolution_report(
        package,
        results['analysis_results'],
        results['version_timeline']
    ))