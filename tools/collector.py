from github import Github
import os

class IssueCollector:
    def __init__(self, github_token=None):
        token = github_token or os.getenv('GITHUB_TOKEN')
        if not token:
            raise ValueError("GitHub token required")
        
        self.gh = Github(token)
    
    def collect(self, repo_name, limit=10):
        """Collect issues from a repository"""
        
        print(f"Collecting from {repo_name}...")
        
        repo = self.gh.get_repo(repo_name)
        
        # Get issues (not PRs)
        issues = repo.get_issues(state='all')
        
        # Collect until we have 'limit' non-PR issues
        collected = []
        for issue in issues:
            if issue.pull_request:
                continue  # Skip pull requests
            
            collected.append({
                'number': issue.number,
                'title': issue.title,
                'body': issue.body or "",
                'state': issue.state,
                'url': issue.html_url
            })
            
            if len(collected) >= limit:
                break
        
        print(f"Found {len(collected)} issues")
        
        return collected