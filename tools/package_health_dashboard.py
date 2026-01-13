import json
from pathlib import Path
from datetime import datetime, timedelta
from collections import defaultdict
from datetime import timezone

def get_package_health(package_name, months=3, classified_file="issues_with_classifications_21k.jsonl"):

    print(f"\n Analyzing health for {package_name} (last {months} months)...")

    now = datetime.now(timezone.utc)
    recent_start = now - timedelta(days=months * 30)
    comparison_start = recent_start - timedelta(days=months * 30)
  
    bugs = load_package_bugs(classified_file, package_name)
    
    if not bugs:
        return f" No bugs found for package '{package_name}'"
    
    current_state = get_current_state(package_name)
    
    recent_bugs = [b for b in bugs if b['created_dt'] >= recent_start]
    comparison_bugs = [b for b in bugs if comparison_start <= b['created_dt'] < recent_start]
    
    recent_comp = calculate_composition(recent_bugs)
    comparison_comp = calculate_composition(comparison_bugs)
    
    trends = calculate_trends(recent_comp, comparison_comp)
    
    alerts = generate_alerts(trends, current_state)
    
    health_score = calculate_health_score(recent_comp, trends)
    
    report = format_dashboard(
        package_name,
        months,
        current_state,
        recent_comp,
        comparison_comp,
        trends,
        alerts,
        health_score
    )
    
    return report


def load_package_bugs(classified_file, package_name):
    if not Path(classified_file).exists():
        return None
    
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
                    try:
                        bug['created_dt'] = datetime.fromisoformat(bug['created_at'].replace('Z', '+00:00')).replace(tzinfo=timezone.utc)
                        bugs.append(bug)
                    except Exception:
                        continue
                        
            except json.JSONDecodeError:
                continue
    
    return bugs


def get_current_state(package_name):
    import requests
    
    try:
        response = requests.get(f"https://registry.npmjs.org/{package_name}/latest", timeout=10)
        if response.status_code != 200:
            return None
        
        data = response.json()

        dependencies = data.get('dependencies', {})
        peer_dependencies = data.get('peerDependencies', {})
        optional_dependencies = data.get('optionalDependencies', {})
        
        production_deps = len(dependencies) + len(peer_dependencies) + len(optional_dependencies)

        version = data.get('version', 'unknown')

        full_response = requests.get(f"https://registry.npmjs.org/{package_name}", timeout=10)
        if full_response.status_code == 200:
            full_data = full_response.json()
            last_release = full_data.get('time', {}).get(version, 'unknown')
            if last_release != 'unknown':
                last_release = last_release[:10]  # YYYY-MM-DD
        else:
            last_release = 'unknown'
        
        return {
            'version': version,
            'production_deps': production_deps,
            'last_release': last_release
        }
        
    except Exception:
        return None


def calculate_composition(bugs):

    if not bugs:
        return {
            'total': 0,
            'intrinsic': 0,
            'extrinsic': 0,
            'not_bug': 0,
            'unknown': 0,
            'intrinsic_pct': 0.0,
            'extrinsic_pct': 0.0,
            'not_bug_pct': 0.0,
            'unknown_pct': 0.0
        }
    
    counts = defaultdict(int)
    for bug in bugs:
        classification = bug.get('final_classification', 'Unknown')
        counts[classification] += 1
    
    total = len(bugs)
    
    return {
        'total': total,
        'intrinsic': counts['Intrinsic'],
        'extrinsic': counts['Extrinsic'],
        'not_bug': counts['Not  a Bug'],
        'unknown': counts['Unknown'],
        'intrinsic_pct': round(counts['Intrinsic'] / total * 100, 1),
        'extrinsic_pct': round(counts['Extrinsic'] / total * 100, 1),
        'not_bug_pct': round(counts['Not  a Bug'] / total * 100, 1),
        'unknown_pct': round(counts['Unknown'] / total * 100, 1)
    }


def calculate_trends(recent, comparison):
    """Calculate trend changes"""
    
    extrinsic_change = recent['extrinsic_pct'] - comparison['extrinsic_pct']
    intrinsic_change = recent['intrinsic_pct'] - comparison['intrinsic_pct']
    
    return {
        'extrinsic_change': round(extrinsic_change, 1),
        'intrinsic_change': round(intrinsic_change, 1),
        'extrinsic_trend': 'INCREASING' if extrinsic_change > 5 else 'DECREASING' if extrinsic_change < -5 else 'STABLE',
        'intrinsic_trend': 'INCREASING' if intrinsic_change > 5 else 'DECREASING' if intrinsic_change < -5 else 'STABLE'
    }


def generate_alerts(trends, current_state):

    
    alerts = []

    if trends['extrinsic_change'] > 5:
        alerts.append(f"  Extrinsic bugs increased by {trends['extrinsic_change']:+.1f} percentage points")
    if trends['intrinsic_change'] > 5:
        alerts.append(f"  Intrinsic bugs increased by {trends['intrinsic_change']:+.1f} percentage points")
    if trends['extrinsic_change'] < -5:
        alerts.append(f" Extrinsic bugs decreased by {abs(trends['extrinsic_change']):.1f} percentage points")  
    if trends['intrinsic_change'] < -5:
        alerts.append(f" Intrinsic bugs decreased by {abs(trends['intrinsic_change']):.1f} percentage points")
    
    if not alerts:
        alerts.append("  No significant trend changes detected")
    
    return alerts


def calculate_health_score(recent_comp, trends):
    score = 10.0

    score -= recent_comp['extrinsic_pct'] / 2
    score -= recent_comp['intrinsic_pct'] / 4

    if trends['extrinsic_change'] > 0:
        score -= trends['extrinsic_change'] / 5
    
    if trends['intrinsic_change'] > 0:
        score -= trends['intrinsic_change'] / 10
        
    score = max(1.0, min(10.0, score))
    
    return round(score, 1)


def format_dashboard(package_name, months, current_state, recent, comparison, trends, alerts, health_score):
    
    output = []
    output.append("\n" + "=" * 70)
    output.append(f" {package_name.upper()} HEALTH DASHBOARD")
    output.append("=" * 70)
    output.append(f"Analysis Period: Last {months} months")
    output.append(f"Generated: {datetime.now().strftime('%Y-%m-%d')}")
    
    if current_state:
        output.append(f"\n CURRENT STATE:")
        output.append(f"   Latest version: v{current_state['version']}")
        output.append(f"   Production deps: {current_state['production_deps']}")
        output.append(f"   Last release: {current_state['last_release']}")
    else:
        output.append(f"\n CURRENT STATE:")
        output.append(f"     Unable to fetch current npm data")
    
    output.append(f"\n RECENT ACTIVITY (Last {months} months):")
    output.append(f"   Total bugs: {recent['total']}")
    output.append(f"   - Intrinsic: {recent['intrinsic']} ({recent['intrinsic_pct']:.1f}%)")
    output.append(f"   - Extrinsic: {recent['extrinsic']} ({recent['extrinsic_pct']:.1f}%)")
    output.append(f"   - Not a Bug: {recent['not_bug']} ({recent['not_bug_pct']:.1f}%)")
    output.append(f"   - Unknown: {recent['unknown']} ({recent['unknown_pct']:.1f}%)")
    
    output.append(f"\n COMPARISON ({months} months before):")
    output.append(f"   Total bugs: {comparison['total']}")
    output.append(f"   - Intrinsic: {comparison['intrinsic']} ({comparison['intrinsic_pct']:.1f}%)")
    output.append(f"   - Extrinsic: {comparison['extrinsic']} ({comparison['extrinsic_pct']:.1f}%)")
    output.append(f"   - Not a Bug: {comparison['not_bug']} ({comparison['not_bug_pct']:.1f}%)")
    output.append(f"   - Unknown: {comparison['unknown']} ({comparison['unknown_pct']:.1f}%)")
    
    output.append(f"\n TRENDS:")
    
    ex_arrow = "⬆️" if trends['extrinsic_change'] > 0 else "⬇️" if trends['extrinsic_change'] < 0 else "➡️"
    in_arrow = "⬆️" if trends['intrinsic_change'] > 0 else "⬇️" if trends['intrinsic_change'] < 0 else "➡️"
    
    output.append(f"   Extrinsic: {comparison['extrinsic_pct']:.1f}% → {recent['extrinsic_pct']:.1f}% ({trends['extrinsic_change']:+.1f}% {ex_arrow} {trends['extrinsic_trend']})")
    output.append(f"   Intrinsic: {comparison['intrinsic_pct']:.1f}% → {recent['intrinsic_pct']:.1f}% ({trends['intrinsic_change']:+.1f}% {in_arrow} {trends['intrinsic_trend']})")
    
    output.append(f"\n  ALERTS:")
    for alert in alerts:
        output.append(f"   {alert}")

    score_emoji = "🟢" if health_score >= 7 else "🟡" if health_score >= 5 else "🔴"
    score_label = "EXCELLENT" if health_score >= 8 else "GOOD" if health_score >= 7 else "FAIR" if health_score >= 5 else "NEEDS ATTENTION"
    
    output.append(f"\n{score_emoji} HEALTH SCORE: {health_score}/10 ({score_label})")
    
    output.append("\n" + "=" * 70)
    
    return "\n".join(output)

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python package_health_dashboard.py <package_name> [months]")
        print("\nExamples:")
        print("  python package_health_dashboard.py axios")
        print("  python package_health_dashboard.py laravel-mix 6")
        sys.exit(1)
    
    package = sys.argv[1]
    months = int(sys.argv[2]) if len(sys.argv) > 2 else 3
    
    report = get_package_health(package, months)
    print(report)