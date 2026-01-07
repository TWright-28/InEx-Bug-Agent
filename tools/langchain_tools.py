from langchain.tools import Tool
from pydantic import BaseModel, Field
from tools.collector import IssueCollector
from tools.classifier import BugClassifier
from typing import Optional
from dotenv import load_dotenv
import json
from datetime import datetime
import os

load_dotenv()

# Initialize once
collector = IssueCollector()
classifier = BugClassifier()

def list_repositories(owner: str, limit: int = 20) -> str:
    """List repositories for a GitHub user or organization"""
    repos = collector.list_repos(owner, limit)
    
    if not repos:
        return f"Could not find repositories for '{owner}'"
    
    result = f"Found {len(repos)} repositories for {owner}:\n\n"
    
    for i, repo in enumerate(repos, 1):
        result += f"{i}. {repo['full_name']}\n"
        result += f"   {repo['description'][:80]}...\n" if len(repo['description']) > 80 else f"   {repo['description']}\n"
        result += f"   Stars: {repo['stars']} | Open Issues: {repo['open_issues']} | Language: {repo['language']}\n\n"
    
    return result

def classify_bugs(repo: str, limit: int = 10) -> str:
    """Classify bugs from a GitHub repository"""
    
    # Collect issues
    print(f"\n Collecting and classifying {limit} issues from {repo}...\n")
    issues = collector.collect(repo, limit)
    
    if not issues:
        return f"No issues found in {repo}"
    
    # Prepare results storage
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    results_file = f"data/results_{timestamp}.jsonl"
    collected_file = f"data/collected_{timestamp}.jsonl"
    log_file = f"data/classification_{timestamp}.log"
    
    # Ensure data directory exists
    os.makedirs('data', exist_ok=True)
    
    # Save collected issues
    print(f" Saving collected issues to {collected_file}...")
    with open(collected_file, 'w', encoding='utf-8') as f:
        for issue in issues:
            f.write(json.dumps(issue, ensure_ascii=False) + '\n')
    
    # Open log file
    with open(log_file, 'w', encoding='utf-8') as log:
        log.write(f"Classification started at {datetime.now().isoformat()}\n")
        log.write(f"Repository: {repo}\n")
        log.write(f"Limit: {limit}\n")
        log.write(f"Total issues collected: {len(issues)}\n")
        log.write(f"Collected data saved to: {collected_file}\n")
        log.write("="*80 + "\n\n")
        
        # Classify each
        results = []
        for i, issue in enumerate(issues, 1):
            print(f"  Classifying {i}/{len(issues)}...")
            
            # Log to file
            log.write(f"[{i}/{len(issues)}] Issue #{issue['number']}: {issue['title']}\n")
            log.flush()
            
            classification = classifier.classify(issue)
            
            result = {
                'timestamp': datetime.now().isoformat(),
                'repo': repo,
                'number': issue['number'],
                'title': issue['title'],
                'url': issue['url'],
                'state': issue['state'],
                'classification': classification['classification'],
                'reasoning': classification['reasoning'],
                'probabilities': classification.get('probabilities', {}),
                'raw_response': classification.get('raw_response', '')
            }
            
            results.append(result)
            
            # Save incrementally to JSONL
            with open(results_file, 'a', encoding='utf-8') as f:
                f.write(json.dumps(result, ensure_ascii=False) + '\n')
            
            # Log result
            log.write(f"  Classification: {classification['classification']}\n")
            log.write(f"  Reasoning (first 200 chars): {classification['reasoning'][:200]}...\n")
            log.write("\n")
            log.flush()
    
    # Summarize
    intrinsic = len([r for r in results if r['classification'] == 'INTRINSIC'])
    extrinsic = len([r for r in results if r['classification'] == 'EXTRINSIC'])
    not_bug = len([r for r in results if r['classification'] == 'NOT_A_BUG'])
    unknown = len([r for r in results if r['classification'] == 'UNKNOWN'])
    
    summary = f"""
Classified {len(results)} issues from {repo}:
  • Intrinsic: {intrinsic}
  • Extrinsic: {extrinsic}
  • Not a Bug: {not_bug}
  • Unknown: {unknown}

Results saved to: {results_file}
Collected data saved to: {collected_file}
Log saved to: {log_file}

Top issues:
"""
    
    for r in results[:5]:
        summary += f"  • #{r['number']}: {r['title'][:60]}... ({r['classification']})\n"
    
    return summary


def collect_bugs(repo: str, limit: int = 10) -> str:
    """Collect bug data from a GitHub repository WITHOUT classification"""
    
    print(f"\n Collecting {limit} issues from {repo}...\n")
    issues = collector.collect(repo, limit)
    
    if not issues:
        return f"No issues found in {repo}"
    
    # Prepare storage
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    collected_file = f"data/collected_{timestamp}.jsonl"
    
    # Ensure data directory exists
    os.makedirs('data', exist_ok=True)
    
    # Save collected issues
    print(f" Saving collected issues to {collected_file}...")
    with open(collected_file, 'w', encoding='utf-8') as f:
        for issue in issues:
            f.write(json.dumps(issue, ensure_ascii=False) + '\n')
    
    # Summarize (NO classification info)
    summary = f"""
Collected {len(issues)} issues from {repo}:

Collected data saved to: {collected_file}

Top issues:
"""
    
    for i, issue in enumerate(issues[:5], 1):
        state = issue.get('state', 'unknown')
        summary += f"  • #{issue['number']}: {issue['title'][:60]}... ({state})\n"
    
    summary += f"\nData collected successfully. To classify these issues, run classification separately."
    
    return summary


def _safe_collect_bugs(input_str):
    """Safely parse and call collect_bugs"""
    try:
        parts = input_str.split(',')
        
        if len(parts) == 1:
            repo = parts[0].strip()
            limit = 10
        elif len(parts) == 2:
            repo = parts[0].strip()
            limit_str = parts[1].strip()
            
            try:
                limit = int(limit_str)
            except ValueError:
                return f"Error: limit must be a number, got '{limit_str}'"
        else:
            return f"Error: Invalid input format. Use 'owner/repo,limit' (e.g., 'facebook/react,5')"
        
        if '/' not in repo:
            return f"Error: Repository must be in 'owner/repo' format (e.g., 'facebook/react', not just 'react')"
        
        repo_parts = repo.split('/')
        if len(repo_parts) != 2:
            return f"Error: Repository must be 'owner/repo' format, got '{repo}'"
        
        return collect_bugs(repo, limit)
        
    except Exception as e:
        return f"Error parsing input: {str(e)}\nExpected format: 'owner/repo,limit' (e.g., 'facebook/react,5')"



def merge_classifications(collected_file: str, results_file: str, output_file: str = "issues_with_classifications.jsonl") -> str:
    """
    Merge classification results back into collected data.
    
    Args:
        collected_file: Path to collected_TIMESTAMP.jsonl
        results_file: Path to results_TIMESTAMP.jsonl  
        output_file: Path to output merged file (default: issues_with_classifications.jsonl)
    
    Returns:
        Success message with output file path
    """
    import json
    
    try:
        # Load collected data
        print(f"Loading collected data from {collected_file}...")
        collected = {}
        with open(collected_file, 'r', encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    issue = json.loads(line)
                    key = (issue['owner'], issue['repo'], issue['number'])
                    collected[key] = issue
        
        print(f"  Loaded {len(collected)} issues")
        
        # Load classification results
        print(f"Loading classifications from {results_file}...")
        classifications = {}
        with open(results_file, 'r', encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    result = json.loads(line)
                    repo_parts = result['repo'].split('/')
                    if len(repo_parts) == 2:
                        owner, repo = repo_parts
                        key = (owner, repo, result['number'])
                        classifications[key] = result
        
        print(f"  Loaded {len(classifications)} classifications")
        
        # Merge
        print(f"Merging...")
        merged_count = 0
        
        with open(output_file, 'w', encoding='utf-8') as f:
            for key, issue in collected.items():
                if key in classifications:
                    result = classifications[key]
                    
                    # Map classification format
                    classification = result['classification']
                    if classification == 'NOT_A_BUG':
                        final_class = 'Not  a Bug'  # Two spaces for analysis.py
                    else:
                        final_class = classification.capitalize()
                    
                    # Add ALL classification fields
                    issue['final_classification'] = final_class
                    issue['classification'] = result['classification']
                    issue['classification_reasoning'] = result.get('reasoning', '')
                    issue['classification_probabilities'] = result.get('probabilities', {})
                    issue['classification_raw_response'] = result.get('raw_response', '')
                    issue['classification_timestamp'] = result.get('timestamp', '')
                    issue['classification_url'] = result.get('url', '')
                    
                    merged_count += 1
                else:
                    # No classification found
                    issue['final_classification'] = 'Unknown'
                    issue['classification'] = 'UNKNOWN'
                    issue['classification_reasoning'] = 'Not classified'
                    issue['classification_probabilities'] = {}
                    issue['classification_raw_response'] = ''
                    issue['classification_timestamp'] = ''
                    issue['classification_url'] = ''
                
                # Write to output
                f.write(json.dumps(issue, ensure_ascii=False) + '\n')
        
        return f""" Successfully merged {merged_count}/{len(collected)} issues
Output saved to: {output_file}

IMPORTANT: Use this file for analysis: {output_file}
"""
    
    except Exception as e:
        return f"Error merging classifications: {str(e)}"


def analyze_classifications(input_file: str = "issues_with_classifications.jsonl") -> str:
    """
    Run comprehensive analysis on classified issues and generate figures.
    
    Args:
        input_file: Path to merged JSONL file with classifications
    
    Returns:
        Summary of analysis with file locations
    """
    import subprocess
    import sys
    
    try:
        # Check if file exists
        if not os.path.exists(input_file):
            return f"Error: File not found: {input_file}\nPlease merge classifications first."
        
        print(f"\n Running analysis on {input_file}...\n")
        
        # Run analysis.py as a module
        result = subprocess.run(
            [sys.executable, '-m', 'tools.analysis', input_file],
            capture_output=True,
            text=True,
            timeout=300  # 5 minute timeout
        )
        
        # Check for errors
        if result.returncode != 0:
            return f"Analysis failed:\n{result.stderr}"
        
        # Return output
        output = result.stdout
        
        summary = f"""
 Analysis complete!

Generated files:
  • figures/comprehensive_analysis.png
  • figures/sankey_flow.png
  • figures/repo_distribution.png
  • figures/time_to_close.png
  • closed_by_summary.txt

{output}
"""
        
        return summary
    
    except subprocess.TimeoutExpired:
        return "Analysis timed out (took longer than 5 minutes)"
    except Exception as e:
        return f"Error running analysis: {str(e)}"

def _safe_classify_bugs(input_str):
    """Safely parse and call classify_bugs with better error handling"""
    try:
        parts = input_str.split(',')
        
        if len(parts) == 1:
            # Only repo given, no limit
            repo = parts[0].strip()
            limit = 10
        elif len(parts) == 2:
            repo = parts[0].strip()
            limit_str = parts[1].strip()
            
            # Try to parse limit
            try:
                limit = int(limit_str)
            except ValueError:
                return f"Error: limit must be a number, got '{limit_str}'"
        else:
            return f"Error: Invalid input format. Use 'owner/repo,limit' (e.g., 'facebook/react,5')"
        
        # Check if repo has owner/repo format
        if '/' not in repo:
            return f"Error: Repository must be in 'owner/repo' format (e.g., 'prettier/prettier', not just 'prettier')"
        
        # Validate repo format
        repo_parts = repo.split('/')
        if len(repo_parts) != 2:
            return f"Error: Repository must be 'owner/repo' format, got '{repo}'"
        
        # Call the actual function
        return classify_bugs(repo, limit)
        
    except Exception as e:
        return f"Error parsing input: {str(e)}\nExpected format: 'owner/repo,limit' (e.g., 'facebook/react,5')"

def _safe_analyze_classifications(input_str):
    """Safely parse and call analyze_classifications"""
    try:
        # Clean the input
        input_file = input_str.strip().strip('"').strip("'")
        
        if not input_file:
            input_file = "issues_with_classifications.jsonl"
        
        if not os.path.exists(input_file):
            return f"Error: File not found: {input_file}\n\nAvailable files:\n" + "\n".join(
                [f"  - {f}" for f in os.listdir('.') if f.endswith('.jsonl')]
            )
        
        return analyze_classifications(input_file)
        
    except Exception as e:
        return f"Error: {str(e)}"



def _safe_list_repos(input_str):
    """Safely parse and call list_repositories"""
    try:
        owner = input_str.strip()
        
        if not owner:
            return "Error: Please provide a GitHub username or organization name"
        
        # Remove any extra characters
        owner = owner.split(',')[0].split()[0]
        
        return list_repositories(owner, 20)
        
    except Exception as e:
        return f"Error: {str(e)}"

# Update the tool


def _safe_merge_classifications(input_str):
    """Safely parse and call merge_classifications"""
    try:
        # Clean the input string
        input_str = input_str.strip().strip('"').strip("'")
        
        parts = [p.strip() for p in input_str.split(',')]
        
        if len(parts) == 2:
            # No output file specified, use default
            collected_file = parts[0]
            results_file = parts[1]
            output_file = "issues_with_classifications.jsonl"
        elif len(parts) == 3:
            collected_file = parts[0]
            results_file = parts[1]
            output_file = parts[2]
        else:
            return f"Error: Expected 2-3 files separated by commas.\nFormat: 'collected.jsonl,results.jsonl' or 'collected.jsonl,results.jsonl,output.jsonl'"
        
        # Check files exist
        if not os.path.exists(collected_file):
            return f"Error: Collected file not found: {collected_file}"
        if not os.path.exists(results_file):
            return f"Error: Results file not found: {results_file}"
        
        return merge_classifications(collected_file, results_file, output_file)
        
    except Exception as e:
        return f"Error parsing merge input: {str(e)}"




# Create tools
# Create tools
tools = [
    Tool(
        name="list_repositories",
        func=lambda input_str: _safe_list_repos(input_str),
        description="List GitHub repositories for a user or organization. Input should be just the username or organization name (e.g., 'google', 'facebook', 'microsoft')."
    ),
    Tool(
        name="collect_bugs",  # ← NEW TOOL
        func=lambda input_str: _safe_collect_bugs(input_str),
        description="""Collect bug data from a GitHub repository WITHOUT classification.
        
Input format: "owner/repo,limit" where limit is a number

Examples:
  - "facebook/react,5" - collect 5 issues (no classification)
  - "google/leveldb,10" - collect 10 issues (no classification)

This ONLY fetches data from GitHub. No classification is performed.
To classify bugs, use classify_bugs instead."""
    ),
    Tool(
        name="classify_bugs",
        func=lambda input_str: _safe_classify_bugs(input_str),
        description="""Collect AND classify bugs from a GitHub repository.
        
Input format: "owner/repo,limit" where limit is a number

Examples:
  - "facebook/react,5" - collect and classify 5 bugs
  - "google/leveldb,10" - collect and classify 10 bugs

This fetches data from GitHub AND runs classification on each issue.
To just collect data without classification, use collect_bugs instead."""
    ),
    Tool(
        name="merge_classifications",
        func=lambda input_str: _safe_merge_classifications(input_str),
        description="""Merge classification results with collected data.
    
Input format: "collected_file.jsonl,results_file.jsonl,output_file.jsonl"
The output file is optional (defaults to issues_with_classifications.jsonl)

Examples:
  - "data/collected_20260107.jsonl,data/results_20260107.jsonl"
  - "data/collected_20260107.jsonl,data/results_20260107.jsonl,merged.jsonl"
"""
    ),
    Tool(
        name="analyze_classifications",
        func=lambda input_str: _safe_analyze_classifications(input_str),
        description="""Run comprehensive analysis on classified issues.
    
Input: Path to a merged JSONL file with classifications (file must have 'final_classification' field)

Example: "issues_with_classifications.jsonl"

This generates statistics and visualizations in the figures/ directory."""
    )
]

def create_tools():
    """Return the list of tools for the agent"""
    return tools