import json
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import seaborn as sns
from matplotlib.patches import Rectangle
import os

KNOWN_BOTS = {"stale[bot]", "vue-bot"}
BUG_TYPES_ORDER = ['Intrinsic', 'Extrinsic', 'Not  a Bug', 'Unknown']
COLOR_PALETTE = {
    'Intrinsic': '#5B9BD5',
    'Extrinsic': '#ED7D31',
    'Not  a Bug': '#70AD47',
    'Unknown': '#FFC000'
}


def _closed_by_username(row):
    x = row.get("closed_by")
    return x.get("username") if isinstance(x, dict) and x.get("username") else "Unknown"

def _bot_closed_mask(df):
    df_local = df
    if "closed_by_username" not in df.columns:
        df_local = df.copy()
        df_local["closed_by_username"] = df_local.apply(_closed_by_username, axis=1)
    is_closed = df_local["state"].str.lower().eq("closed")
    return is_closed & df_local["closed_by_username"].isin(KNOWN_BOTS)

def _fmt_pct(col):
    return col.map(lambda v: f"{v:.2f}%" if pd.notnull(v) else "")

def _sec_series(series, key):

    vals, idx = [], []
    for i, x in series.items():
        if isinstance(x, dict) and isinstance(x.get(key), (int, float)):
            vals.append(float(x[key]))
        else:
            vals.append(None)
        idx.append(i)
    return pd.Series(vals, index=idx, dtype="float")

def _prepare_dataframe(df):
    """Add computed columns to dataframe for easier analysis."""
    df = df.copy()
    
    df['bug_type'] = df['final_classification'].str.strip()
    
    df['is_closed'] = df['state'].str.lower() == 'closed'
    
    df['time_to_close_days'] = df['timestamp_metrics'].apply(
        lambda x: x['time_to_close_seconds'] / 86400 if isinstance(x, dict) and 
        isinstance(x.get('time_to_close_seconds'), (int, float)) else None
    )
    
    
    df['closed_by_username'] = df.apply(_closed_by_username, axis=1)
    
    df['bot_closed'] = _bot_closed_mask(df)
    
    df["closed_by_pr"] = df["closing_pr"].apply(
        lambda x: isinstance(x, dict) and len(x) > 0 if pd.notna(x) else False
    )
    df["closed_by_commit"] = df["closing_commit"].apply(
        lambda x: isinstance(x, dict) and len(x) > 0 if pd.notna(x) else False
    )
    
    if 'project' not in df.columns:
        if 'owner' in df.columns and 'repo' in df.columns:
            df['project'] = df['owner'] + '/' + df['repo']
    
    return df


def load_data(path="issues.jsonl"):
    """Load JSONL data into a pandas DataFrame."""
    print(f"Loading data from {path}...")
    with open(path, "r", encoding="utf-8") as f:
        data = [json.loads(line) for line in f]
    df = pd.DataFrame(data)
    return _prepare_dataframe(df)


def analyze_bot_closures(df):
    print("\n" + "="*70)
    print("SECTION 1: BOT-CLOSED ISSUES")
    print("="*70)
    
    total_bot = int(df['bot_closed'].sum())
    total_all = len(df)
    print(f"\nBot-closed issues: {total_bot}/{total_all} ({(total_bot/total_all*100):.2f}%)")

    by_class = (
        pd.DataFrame({"bot_closed": df['bot_closed'], "class": df["bug_type"]})
        .groupby("class")["bot_closed"]
        .agg(count="sum", total="count")
    )
    by_class["pct"] = (by_class["count"] / by_class["total"] * 100).round(2)
    print("\nBot-closed by class (count / total, %):")
    print(by_class)

def analyze_class_distribution(df):
    print("\n" + "="*70)
    print("SECTION 2: CLASS DISTRIBUTION")
    print("="*70)
    
    counts = df["bug_type"].value_counts().sort_index()
    pct = counts / counts.sum() * 100
    tbl = pd.DataFrame({"Count": counts, "Percent": _fmt_pct(pct)})
    print("\n" + tbl.to_string())

def analyze_closed_ratio(df):
    print("\n" + "-"*70)
    print("Closed Ratio (All Issues vs Excluding Bots)")
    print("-"*70)
    
    # Closed % for all issues
    t_all = (df.groupby("bug_type")['is_closed']
               .mean().mul(100).round(2)
               .rename("Closed % (All)"))

    is_closed_by_human = df['is_closed'] & ~df['bot_closed']
    t_nb = (df.assign(_closed_human=is_closed_by_human)
               .groupby("bug_type")["_closed_human"]
               .mean().mul(100).round(2)
               .rename("Closed % (No Bots)"))

    out = pd.concat([t_all, t_nb], axis=1).sort_index()
    out["Closed % (All)"] = _fmt_pct(out["Closed % (All)"])
    out["Closed % (No Bots)"] = _fmt_pct(out["Closed % (No Bots)"])
    print("\n" + out.to_string())

def analyze_comments(df):
    """Calculate average, median, and P90 comments per classification."""
    print("\n" + "-"*70)
    print("Comment Statistics by Class")
    print("-"*70)
    
    result = (
        df.groupby("bug_type")["comments_count"]
        .agg(Mean="mean", Median="median", P90=lambda s: s.quantile(0.9))
        .round(2)
    )
    print("\n" + result.to_string())


def analyze_time_to_close(df):
    print("\n" + "="*70)
    print("SECTION 3: TIMING ANALYSIS")
    print("="*70)
    print("\nTime to Close (days): All Issues vs Excluding Bots")
    print("-"*70)
    
    # All issues
    days_all = _sec_series(df["timestamp_metrics"], "time_to_close_seconds") / 86400.0
    g_all = (df.assign(_days=days_all)
               .groupby("bug_type")["_days"]
               .agg(Mean="mean", Median="median", P90=lambda s: s.quantile(0.9)).round(2))
    g_all.columns = [f"{c} (All)" for c in g_all.columns]

    # No bots
    df_nb = df.loc[~df['bot_closed']].copy()
    days_nb = _sec_series(df_nb["timestamp_metrics"], "time_to_close_seconds") / 86400.0
    g_nb = (df_nb.assign(_days=days_nb)
                 .groupby("bug_type")["_days"]
                 .agg(Mean="mean", Median="median", P90=lambda s: s.quantile(0.9)).round(2))
    g_nb.columns = [f"{c} (No Bots)" for c in g_nb.columns]

    out = g_all.join(g_nb, how="outer").sort_index()
    print("\n" + out.to_string())

def analyze_time_to_first_response(df):
    print("\n" + "-"*70)
    print("Time to First Response (hours)")
    print("-"*70)
    
    hrs = _sec_series(df["timestamp_metrics"], "time_to_first_response_seconds") / 3600.0
    result = (df.assign(_hrs=hrs)
             .groupby("bug_type")["_hrs"]
             .agg(Mean="mean", Median="median", P90=lambda s: s.quantile(0.9))
             .round(2))
    print("\n" + result.to_string())

def analyze_maintainer_involvement(df):
    print("\n" + "="*70)
    print("SECTION 4: MAINTAINER INVOLVEMENT")
    print("="*70)
    
    rows = []
    for _, row in df.iterrows():
        m = row.get("participant_metrics")
        if isinstance(m, dict):
            rows.append({
                "bug_type": row.get("bug_type"),
                "has_maint": 1 if m.get("has_maintainer_response") else 0,
                "maintainers": m.get("maintainer_participants", None),
                "participants": m.get("total_participants", None),
            })
    
    if not rows:
        print("\nNo maintainer data available.")
        return

    tmp = pd.DataFrame(rows)
    result = (tmp.groupby("bug_type")
             .agg(
                 Response_Rate=("has_maint", lambda s: s.mean() * 100),
                 Avg_Maintainers=("maintainers", "mean"),
                 Avg_Participants=("participants", "mean"),
             )
             .round(2))
    result["Response_Rate"] = _fmt_pct(result["Response_Rate"])
    print("\n" + result.to_string())

def analyze_maintainer_ratio(df):
    print("\n" + "-"*70)
    print("Maintainer Participation Ratio (% of total participants)")
    print("-"*70)
    
    rows = []
    for _, row in df.iterrows():
        metrics = row.get("participant_metrics")
        if isinstance(metrics, dict):
            total = metrics.get("total_participants")
            maint = metrics.get("maintainer_participants")
            if isinstance(total, (int, float)) and isinstance(maint, (int, float)) and total > 0:
                ratio = maint / total
                rows.append({"bug_type": row.get("bug_type"), "ratio": ratio})

    if not rows:
        print("\nNo valid participant data found.")
        return

    result = (
        pd.DataFrame(rows)
        .groupby("bug_type")["ratio"]
        .agg(Mean="mean", Median="median", P90=lambda s: s.quantile(0.9))
        .mul(100)
        .round(2)
    )
    print("\n" + result.to_string())
    
def analyze_reopens(df):
    print("\n" + "="*70)
    print("SECTION 5: REOPEN STATISTICS (Excluding Bot-Closed)")
    print("="*70)
    
    df_nb = df.loc[~df['bot_closed']].copy()

    rows = []
    for _, row in df_nb.iterrows():
        r = row.get("reopen_metrics")
        if isinstance(r, dict):
            rows.append({
                "bug_type": row.get("bug_type"),
                "was_reopened": 1 if r.get("was_reopened") else 0,
                "reopen_count": r.get("reopen_count", None),
                "time_to_reopen_days": (r.get("time_to_reopen_seconds") / 86400.0
                                        if isinstance(r.get("time_to_reopen_seconds"), (int, float)) else None),
            })
    
    if not rows:
        print("\nNo reopen data available.")
        return

    tmp = pd.DataFrame(rows)
    result = (tmp.groupby("bug_type")
             .agg(
                 Count=("was_reopened", "sum"),
                 Percentage=("was_reopened", lambda s: s.mean() * 100),
                 Avg_Count=("reopen_count", "mean"),
                 Avg_Days_To_Reopen=("time_to_reopen_days", "mean"),
             )
             .round(2))
    result["Percentage"] = _fmt_pct(result["Percentage"])
    print("\n" + result.to_string())


def _categorize_label(label_name):
    name = label_name.lower()
    
    if "bug" in name:
        return "Bug"
    elif any(x in name for x in ["enhancement", "improvement", "feature"]):
        return "Enhancement / Feature"
    elif "question" in name or "help" in name:
        return "Question / Help Wanted"
    elif "doc" in name or "example" in name or "readme" in name or "wiki" in name:
        return "Documentation"
    elif "dependency" in name or "deps" in name or "external" in name:
        return "Dependency"
    elif "stale" in name or "inactivity" in name:
        return "Stale / Inactivity"
    elif "duplicate" in name:
        return "Duplicate"
    elif "invalid" in name or "wontfix" in name or "non-issue" in name or "syntax" in name:
        return "Invalid / Wontfix"
    elif any(x in name for x in ["lang", "typescript", "postcss", "react", "types"]):
        return "Language"
    elif "area:" in name:
        return "Area / Module"
    elif "discussion" in name or "info" in name or "more info" in name or "needs investigation" in name or "need repro" in name:
        return "Discussion / Need Info"
    elif any(x in name for x in ["status:", "triage", "triaged", "evaluating"]):
        return "Status / Triage"
    elif any(x in name for x in ["pull request", " ready for pr", " has pr", "released", "semver"]):
        return "PR / Release"
    elif "difficulty" in name or "beginner" in name:
        return "Difficulty / Beginner"
    elif any(x in name for x in ["rule", "scope:", "import/export", "ordering"]):
        return "Rule / Scope"
    else:
        return "Other"

def analyze_labels(df):
    print("\n" + "="*70)
    print("SECTION 6: LABEL ANALYSIS")
    print("="*70)

    rows = []
    for _, row in df.iterrows():
        issue_class = row.get("bug_type")
        labels = row.get("labels")

        if not labels or not isinstance(labels, list) or len(labels) == 0:
            rows.append((issue_class, "No Label"))
            continue

        for label in labels:
            if isinstance(label, dict) and label.get("name"):
                cat = _categorize_label(label["name"])
                rows.append((issue_class, cat))

    if not rows:
        print("\nNo labels found.")
        return

    tmp = pd.DataFrame(rows, columns=["bug_type", "category"])

    # Raw counts
    counts = (
        tmp.value_counts()
           .rename("count")
           .reset_index()
           .pivot(index="bug_type", columns="category", values="count")
           .fillna(0)
           .astype(int)
           .sort_index()
    )

    dist_all = counts.div(counts.sum(axis=1), axis=0).round(3) * 100

    labeled = counts.drop(columns=["No Label"], errors="ignore")
    dist_labeled = labeled.div(labeled.sum(axis=1), axis=0).round(3) * 100

    print("\nRaw label counts:")
    print(counts)
    print("\n% Distribution (including unlabeled):")
    print(dist_all)
    print("\n% Distribution (only labeled issues):")
    print(dist_labeled)


def _extract_code_stats(row):
    cls = row.get("bug_type", "Unknown")
    src = row.get("closing_pr") if isinstance(row.get("closing_pr"), dict) else row.get("closing_commit")
    
    if not isinstance(src, dict):
        return None
    
    # Stats may be directly on src or under src['stats']
    stats = src.get("stats") if isinstance(src.get("stats"), dict) else src
    
    files = stats.get("files_changed")
    adds = stats.get("additions")
    dels = stats.get("deletions")
    
    if isinstance(files, (int, float)) or isinstance(adds, (int, float)) or isinstance(dels, (int, float)):
        return {
            "bug_type": cls,
            "files_changed": files if isinstance(files, (int, float)) else None,
            "additions": adds if isinstance(adds, (int, float)) else None,
            "deletions": dels if isinstance(dels, (int, float)) else None
        }
    return None

def analyze_code_changes(df):

    print("\n" + "="*70)
    print("SECTION 7: CODE CHANGE ANALYSIS")
    print("="*70)

    rows = [_extract_code_stats(row) for _, row in df.iterrows()]
    rows = [r for r in rows if r is not None]

    if not rows:
        print("\nNo code change data available.")
        return

    df_stats = pd.DataFrame(rows)

    # Overall averages
    overall = df_stats.agg({"files_changed":"mean","additions":"mean","deletions":"mean"}).round(2)
    print("\nOverall Averages:")
    for k, v in overall.items():
        print(f"  {k}: {v}")

    # By classification
    by_class = (
        df_stats.groupby("bug_type")
                .agg({"files_changed":"mean","additions":"mean","deletions":"mean"})
                .round(2)
                .sort_index()
    )
    print("\nAverages by Classification:")
    print(by_class)

def analyze_change_effort(df):
    """Calculate total lines changed (additions + deletions) per classification."""
    print("\n" + "-"*70)
    print("Total Lines Changed (Additions + Deletions)")
    print("-"*70)

    rows = []
    for _, row in df.iterrows():
        stats = _extract_code_stats(row)
        if stats:
            adds = stats.get("additions")
            dels = stats.get("deletions")
            if isinstance(adds, (int, float)) and isinstance(dels, (int, float)):
                rows.append({"bug_type": stats["bug_type"], "total_lines": adds + dels})

    if not rows:
        print("\nNo line change data available.")
        return

    result = (
        pd.DataFrame(rows)
        .groupby("bug_type")["total_lines"]
        .agg(Mean="mean", Median="median", P90=lambda s: s.quantile(0.9))
        .round(2)
    )
    print("\n" + result.to_string())


def analyze_closure_methods(df):
    """
    Analyze how issues were closed: by PR, by commit, or manually.
    Shows breakdown by classification.
    """
    print("\n" + "="*70)
    print("SECTION 8: CLOSURE METHOD ANALYSIS")
    print("="*70)

    total_closed = df['is_closed']
    total_issues = len(df)
    
    # Overall statistics
    closed_by_pr = (df['closed_by_pr'] & total_closed).sum()
    closed_by_commit = (df['closed_by_commit'] & total_closed).sum()
    closed_by_code = closed_by_pr + closed_by_commit
    
    print("\nOverall Closure Methods:")
    print(f"  Closed by PR:     {closed_by_pr}/{total_issues} ({closed_by_pr/total_issues*100:.2f}%)")
    print(f"  Closed by Commit: {closed_by_commit}/{total_issues} ({closed_by_commit/total_issues*100:.2f}%)")
    print(f"  Closed by Code:   {closed_by_code}/{total_issues} ({closed_by_code/total_issues*100:.2f}%)")
    print(f"  Among closed:     {closed_by_code}/{total_closed.sum()} ({closed_by_code/total_closed.sum()*100:.2f}%)")


    rows = []
    for cls, g in df.groupby("bug_type"):
        total = len(g)
        closed = g['is_closed'].sum()
        by_pr = (g['is_closed'] & g['closed_by_pr']).sum()
        by_commit = (g['is_closed'] & g['closed_by_commit']).sum()
        
        rows.append({
            "Classification": cls,
            "Total": total,
            "Closed": closed,
            "By_PR": by_pr,
            "By_Commit": by_commit,
            "By_Code": by_pr + by_commit,
            "% Code": round((by_pr + by_commit) / closed * 100, 2) if closed > 0 else 0.0,
            "% PR": round(by_pr / closed * 100, 2) if closed > 0 else 0.0,
            "% Commit": round(by_commit / closed * 100, 2) if closed > 0 else 0.0
        })
    
    summary = pd.DataFrame(rows).set_index("Classification")
    
    print("\nBreakdown by Classification:")
    print(summary.to_string())


def analyze_issues_per_repo(df):
    """
    Show how many issues each repository has and the distribution
    across classifications.
    """
    print("\n" + "="*70)
    print("SECTION 9: ISSUES PER REPOSITORY")
    print("="*70)

    if 'project' not in df.columns:
        print("\nNo repository information available.")
        return

    counts = (
        df.groupby(["project", "bug_type"])
        .size()
        .unstack(fill_value=0)
        .reset_index()
    )

    counts["Total"] = counts.sum(axis=1, numeric_only=True)
    counts = counts.sort_values("Total", ascending=False)

    print("\n" + counts.to_string(index=False))


def export_closer_summary(df, output_path="closed_by_summary.txt"):
    """
    Export detailed information about who closed issues to a text file.
    Includes overall counts and per-class breakdowns.
    """
    print("\n" + "="*70)
    print("SECTION 10: CLOSER ANALYSIS")
    print("="*70)

    overall_counts = df["closed_by_username"].value_counts()

    per_class_counts = (
        df.groupby("bug_type")["closed_by_username"]
          .value_counts()
          .rename("count")
          .reset_index()
    )

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("GITHUB ISSUE CLOSER ANALYSIS\n")
        f.write("="*70 + "\n\n")
        
        f.write("Top Closers (All Issues)\n")
        f.write("-"*70 + "\n")
        f.write(overall_counts.to_string() + "\n\n")

        f.write("\nBreakdown by Classification\n")
        f.write("="*70 + "\n")
        for cls in sorted(per_class_counts["bug_type"].unique()):
            subset = per_class_counts[per_class_counts["bug_type"] == cls]
            f.write(f"\n{cls}\n")
            f.write("-"*70 + "\n")
            f.write(subset[["closed_by_username", "count"]].to_string(index=False))
            f.write("\n")

    print(f"\n Exported closer summary to: {output_path}")

def _setup_plot_style():
    """Configure matplotlib for publication-quality figures."""
    plt.rcParams['font.size'] = 11
    plt.rcParams['axes.labelsize'] = 12
    plt.rcParams['axes.titlesize'] = 13
    plt.rcParams['xtick.labelsize'] = 10
    plt.rcParams['ytick.labelsize'] = 10
    plt.rcParams['legend.fontsize'] = 10
    plt.rcParams['figure.titlesize'] = 14
    sns.set_style("whitegrid")
    sns.set_palette("colorblind")

def _draw_sankey_flow(ax, df):
    """Draw Sankey-style flow diagram on given axes."""
    bug_types = BUG_TYPES_ORDER
    bug_counts = df['bug_type'].value_counts().reindex(bug_types)
    
    left_x, right_x = 0, 1
    total_height = sum(bug_counts.values)
    
    # Draw left rectangles (bug types)
    y_pos = 0
    left_positions = {}
    for bug_type in bug_types:
        if bug_type in bug_counts.index and pd.notna(bug_counts[bug_type]):
            height = bug_counts[bug_type] / total_height
            rect = Rectangle((left_x, y_pos), 0.12, height,
                            facecolor=COLOR_PALETTE[bug_type], edgecolor='white', 
                            linewidth=2, alpha=0.85)
            ax.add_patch(rect)
            ax.text(left_x - 0.01, y_pos + height/2, f'{bug_type}',
                   ha='right', va='center', fontsize=10, fontweight='bold')
            ax.text(left_x + 0.06, y_pos + height/2, f'{bug_counts[bug_type]}',
                   ha='center', va='center', fontsize=9, color='white', fontweight='bold')
            left_positions[bug_type] = (y_pos, y_pos + height)
            y_pos += height
    
    # Draw right rectangles (states)
    state_closed = df[df['is_closed']].groupby('bug_type').size()
    state_open = df[~df['is_closed']].groupby('bug_type').size()
    
    total_closed = df['is_closed'].sum()
    total_open = (~df['is_closed']).sum()
    closed_height = total_closed / total_height
    open_height = total_open / total_height
    
    rect_closed = Rectangle((right_x - 0.12, 0), 0.12, closed_height,
                            facecolor='#2ecc71', edgecolor='white', linewidth=2, alpha=0.85)
    ax.add_patch(rect_closed)
    ax.text(right_x + 0.01, closed_height/2, f'Closed',
           ha='left', va='center', fontsize=10, fontweight='bold')
    ax.text(right_x - 0.06, closed_height/2, f'{int(total_closed)}',
           ha='center', va='center', fontsize=9, color='white', fontweight='bold')
    
    rect_open = Rectangle((right_x - 0.12, closed_height), 0.12, open_height,
                          facecolor='#e74c3c', edgecolor='white', linewidth=2, alpha=0.85)
    ax.add_patch(rect_open)
    ax.text(right_x + 0.01, closed_height + open_height/2, f'Open',
           ha='left', va='center', fontsize=10, fontweight='bold')
    ax.text(right_x - 0.06, closed_height + open_height/2, f'{int(total_open)}',
           ha='center', va='center', fontsize=9, color='white', fontweight='bold')

    cumulative_closed = 0
    cumulative_open = closed_height
    
    for bug_type in bug_types:
        if bug_type not in left_positions:
            continue
        
        closed_count = state_closed.get(bug_type, 0)
        open_count = state_open.get(bug_type, 0)
        total_count = closed_count + open_count
        
        if total_count == 0:
            continue
        
        left_y_start, left_y_end = left_positions[bug_type]
        left_height = left_y_end - left_y_start

        if closed_count > 0:
            closed_flow_height = closed_count / total_height
            x = [left_x + 0.12, right_x - 0.12, right_x - 0.12, left_x + 0.12]
            y = [left_y_start, 
                 cumulative_closed, 
                 cumulative_closed + closed_flow_height,
                 left_y_start + (closed_count/total_count) * left_height]
            ax.fill(x, y, color=COLOR_PALETTE[bug_type], alpha=0.25, edgecolor='none')
            cumulative_closed += closed_flow_height

        if open_count > 0:
            open_flow_height = open_count / total_height
            left_open_start = left_y_start + (closed_count/total_count) * left_height
            x = [left_x + 0.12, right_x - 0.12, right_x - 0.12, left_x + 0.12]
            y = [left_open_start,
                 cumulative_open,
                 cumulative_open + open_flow_height,
                 left_y_end]
            ax.fill(x, y, color=COLOR_PALETTE[bug_type], alpha=0.25, edgecolor='none')
            cumulative_open += open_flow_height
    
    ax.set_xlim(-0.22, 1.22)
    ax.set_ylim(0, 1)
    ax.set_aspect('equal')
    ax.axis('off')

def _draw_repo_distribution(ax, df):
    """Draw repository distribution boxplot with jittered points."""
    if 'project' not in df.columns:
            ax.text(0.5, 0.5, 'No project data available', 
                    ha='center', va='center', transform=ax.transAxes)
            return

    if len(df['project'].unique()) < 2:
            ax.text(0.5, 0.5, f'Need data from 2+ repositories\n(have {len(df["project"].unique())})', 
                    ha='center', va='center', transform=ax.transAxes)
            return

    project_data = []
    for project in df['project'].unique():
        project_df = df[df['project'] == project]
        total = len(project_df)
        if total >= 2:  
            for bug_type in ['Intrinsic', 'Extrinsic', 'Not  a Bug']:
                count = len(project_df[project_df['bug_type'] == bug_type])
                project_data.append({
                    'project': project,
                    'bug_type': bug_type,
                    'proportion': count / total
                })
    
    if not project_data:
        ax.text(0.5, 0.5, 'Insufficient project data', 
                ha='center', va='center', transform=ax.transAxes)
        return
    
    consensus_df = pd.DataFrame(project_data)
    bug_types_plot = ['Intrinsic', 'Extrinsic', 'Not  a Bug']
    colors_list = [COLOR_PALETTE[bt] for bt in bug_types_plot]
    
    data_to_plot = []
    for bug_type in bug_types_plot:
        bug_data = consensus_df[consensus_df['bug_type'] == bug_type]['proportion'].values
        data_to_plot.append(bug_data)
    
    positions = range(len(bug_types_plot))
    
    bp = ax.boxplot(data_to_plot, positions=positions, widths=0.5,
                    patch_artist=True, showfliers=False,
                    boxprops=dict(linewidth=1.5),
                    whiskerprops=dict(linewidth=1.5),
                    capprops=dict(linewidth=1.5),
                    medianprops=dict(linewidth=2, color='black'))
    
    for patch, color in zip(bp['boxes'], colors_list):
        patch.set_facecolor(color)
        patch.set_alpha(0.7)
    
    # Add jittered points
    for i, bug_type in enumerate(bug_types_plot):
        bug_data = consensus_df[consensus_df['bug_type'] == bug_type]['proportion'].values
        x = np.random.normal(i, 0.04, size=len(bug_data))
        ax.scatter(x, bug_data, alpha=0.25, s=20, color=colors_list[i], 
                   edgecolors='black', linewidth=0.3)
    
    ax.set_xticks(positions)
    ax.set_xticklabels(bug_types_plot, fontsize=10)
    ax.set_ylabel('Proportion (Consensus)', fontsize=11)
    ax.set_xlabel('Bug Classification', fontsize=11)
    ax.set_ylim(-0.05, 1.05)
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.grid(axis='y', alpha=0.3, linestyle='--')
    ax.set_axisbelow(True)

def _draw_time_to_close(ax, df):
    df_closed = df[df['time_to_close_days'].notna()].copy()
    
    # Add check for minimum data
    if len(df_closed) < 3:
        ax.text(0.5, 0.5, f'Insufficient data for time to close analysis\n(need 3+ closed issues, have {len(df_closed)})', 
                ha='center', va='center', transform=ax.transAxes)
        ax.set_title('Time to Close Distribution')
        return
    
    bug_order = ['Intrinsic', 'Extrinsic', 'Not  a Bug']
    data_to_plot = [df_closed[df_closed['bug_type'] == bt]['time_to_close_days'].values 
                    for bt in bug_order if bt in df_closed['bug_type'].values]
    
    # Check if we have any data
    if not data_to_plot or all(len(d) == 0 for d in data_to_plot):
        ax.text(0.5, 0.5, 'No closed issues with time data', 
                ha='center', va='center', transform=ax.transAxes)
        return
    
    positions = range(len(data_to_plot))
    
    bp = ax.boxplot(data_to_plot, positions=positions, widths=0.5,
                    patch_artist=True, showfliers=False,
                    boxprops=dict(linewidth=1.5),
                    whiskerprops=dict(linewidth=1.5),
                    capprops=dict(linewidth=1.5),
                    medianprops=dict(linewidth=2, color='black'))
    
    for patch, bug_type in zip(bp['boxes'], [bt for bt in bug_order if bt in df_closed['bug_type'].values]):
        patch.set_facecolor(COLOR_PALETTE[bug_type])
        patch.set_alpha(0.7)
    
    ax.set_xticks(positions)
    ax.set_xticklabels([bt for bt in bug_order if bt in df_closed['bug_type'].values], fontsize=10)
    ax.set_ylabel('Time to Close (days)', fontsize=11)
    ax.set_xlabel('Bug Classification', fontsize=11)
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.grid(axis='y', alpha=0.3, linestyle='--')
    ax.set_axisbelow(True)
    
    # Add sample sizes
    for i, bug_type in enumerate([bt for bt in bug_order if bt in df_closed['bug_type'].values]):
        n = len(df_closed[df_closed['bug_type'] == bug_type])
        ax.text(i, ax.get_ylim()[1] * 0.95, f'n={n}', ha='center', fontsize=8)

def generate_comprehensive_figure(df, outdir="figures"):
    """Generate comprehensive multi-panel analysis figure."""
    os.makedirs(outdir, exist_ok=True)
    _setup_plot_style()
    
    fig = plt.figure(figsize=(16, 10))
    gs = gridspec.GridSpec(2, 2, figure=fig, hspace=0.3, wspace=0.3)
    
    # Panel A: Sankey flow
    ax1 = fig.add_subplot(gs[0, :])
    _draw_sankey_flow(ax1, df)
    ax1.set_title('(a) Bug Classification Flow to Issue State', 
                 fontsize=13, fontweight='bold', loc='left', pad=10)
    
    # Panel B: Repository distribution
    ax2 = fig.add_subplot(gs[1, 0])
    _draw_repo_distribution(ax2, df)
    ax2.set_title('(b) Distribution Across Repositories', 
                 fontsize=13, fontweight='bold', loc='left')
    
    # Panel C: Time to close
    ax3 = fig.add_subplot(gs[1, 1])
    _draw_time_to_close(ax3, df)
    ax3.set_title('(c) Resolution Time Distribution', 
                 fontsize=13, fontweight='bold', loc='left')
    
    fig.suptitle('Comprehensive Bug Classification Analysis', 
                fontsize=16, fontweight='bold', y=0.995)
    
    plt.savefig(os.path.join(outdir, "comprehensive_analysis.png"), 
                dpi=300, bbox_inches='tight', facecolor='white')
    plt.close()
    
    print(f"\n Generated comprehensive figure: {outdir}/comprehensive_analysis.png")

def generate_standalone_figures(df, outdir="figures"):
    """Generate individual figures for each panel."""
    os.makedirs(outdir, exist_ok=True)
    _setup_plot_style()
    
    # Sankey flow
    fig, ax = plt.subplots(figsize=(10, 6))
    _draw_sankey_flow(ax, df)
    ax.set_title('Bug Classification Flow to Issue State', 
                 fontsize=14, fontweight='bold', pad=15)
    plt.tight_layout()
    plt.savefig(os.path.join(outdir, "sankey_flow.png"), 
                dpi=300, bbox_inches='tight', facecolor='white')
    plt.close()
    
    # Repository distribution
    fig, ax = plt.subplots(figsize=(8, 6))
    _draw_repo_distribution(ax, df)
    ax.set_title('Distribution of Bug Type Proportions Across Repositories', 
                 fontsize=14, fontweight='bold', pad=15)
    plt.tight_layout()
    plt.savefig(os.path.join(outdir, "repo_distribution.png"), 
                dpi=300, bbox_inches='tight', facecolor='white')
    plt.close()
    
    # Time to close
    fig, ax = plt.subplots(figsize=(8, 6))
    _draw_time_to_close(ax, df)
    ax.set_title('Resolution Time Distribution by Bug Type', 
                 fontsize=14, fontweight='bold', pad=15)
    plt.tight_layout()
    plt.savefig(os.path.join(outdir, "time_to_close.png"), 
                dpi=300, bbox_inches='tight', facecolor='white')
    plt.close()
    
    print(f" Generated standalone figures in: {outdir}/")
    print("  - sankey_flow.png")
    print("  - repo_distribution.png")
    print("  - time_to_close.png")

# ============================================================================
# MAIN EXECUTION
# ============================================================================

def main():
    import sys
    
    # Get input file from command line or use default
    input_file = sys.argv[1] if len(sys.argv) > 1 else "issues_with_classifications.jsonl"
    
    print("\n" + "="*70)
    print("GITHUB ISSUE ANALYSIS")
    print("="*70)
    print(f"Input file: {input_file}\n")
    
    # Load data
    df = load_data(input_file)
    
    # Run all analyses
    analyze_bot_closures(df)
    analyze_class_distribution(df)
    analyze_closed_ratio(df)
    analyze_comments(df)
    
    analyze_time_to_close(df)
    analyze_time_to_first_response(df)
    
    analyze_maintainer_involvement(df)
    analyze_maintainer_ratio(df)
    
    analyze_reopens(df)
    
    analyze_labels(df)
    
    analyze_code_changes(df)
    analyze_change_effort(df)
    
    analyze_closure_methods(df)
    
    analyze_issues_per_repo(df)
    
    export_closer_summary(df)
    
    # Generate figures
    generate_comprehensive_figure(df)
    generate_standalone_figures(df)
    
    print("\n" + "="*70)
    print("ANALYSIS COMPLETE")
    print("="*70)

if __name__ == "__main__":
    main()