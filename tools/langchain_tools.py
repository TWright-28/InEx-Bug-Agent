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

# Create tools
tools = [
    Tool(
        name="list_repositories",
        func=lambda owner: list_repositories(owner, 20),
        description="List GitHub repositories for a user or organization. Input should be the GitHub username or organization name (e.g., 'google', 'facebook', 'microsoft')."
    ),
    Tool(
        name="classify_bugs",
        func=lambda input_str: classify_bugs(*input_str.split(',')) if ',' in input_str else classify_bugs(input_str, 10),
        description="Classify bugs from a GitHub repository. Input should be 'owner/repo,limit' where limit is optional (e.g., 'facebook/react,10' or 'google/tensorflow,5'). If no limit specified, defaults to 10."
    )
]

def create_tools():
    """Return the list of tools for the agent"""
    return tools