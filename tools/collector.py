from github import Github
import os
import requests
import time
from datetime import datetime

class IssueCollector:
    def __init__(self, github_token=None):
        token = github_token or os.getenv('GITHUB_TOKEN')
        if not token:
            raise ValueError("GitHub token required. Set GITHUB_TOKEN environment variable.")
        
        self.gh = Github(token)
        self.token = token
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json"
        }
    
    def collect(self, repo_name, limit=10):
        """Collect issues from a repository with full details"""
        
        print(f"Collecting from {repo_name}...")
        
        try:
            repo = self.gh.get_repo(repo_name)
        except Exception as e:
            print(f"Error accessing repo: {e}")
            return []
        
        # Get issues
        issues = repo.get_issues(state='all')
        
        # Collect until we have 'limit' non-PR issues
        collected = []
        for issue in issues:
            if issue.pull_request:
                continue  # Skip pull requests
            
            print(f"   Fetching #{issue.number}: {issue.title[:60]}...")
            
            # Get full details
            issue_data = self._extract_full_issue_data(issue, repo_name)
            collected.append(issue_data)
            
            if len(collected) >= limit:
                break
        
        print(f"   Found {len(collected)} issues")
        return collected
    
    def _extract_full_issue_data(self, issue, repo_name):
        """Extract comprehensive issue data"""
        
        owner, repo = repo_name.split('/')
        number = issue.number
        
        # Fetch additional data via REST API for more details
        comments = self._fetch_comments(owner, repo, number)
        timeline = self._fetch_timeline(owner, repo, number)
        
        # Build comments with author associations
        comments_data = []
        maintainer_comments = []
        
        for comment in comments:
            comment_obj = {
                "id": comment.get("id"),
                "created_at": comment.get("created_at"),
                "updated_at": comment.get("updated_at"),
                "author": {
                    "username": comment.get("user", {}).get("login"),
                    "id": comment.get("user", {}).get("id"),
                    "author_association": comment.get("author_association")
                },
                "body": comment.get("body")
            }
            comments_data.append(comment_obj)
            
            # Track maintainer comments separately
            assoc = comment.get("author_association", "")
            if assoc in ["OWNER", "MEMBER", "COLLABORATOR"]:
                maintainer_comments.append(comment_obj)
        
        # Calculate metrics
        timestamp_metrics = self._calculate_timestamps(issue, comments)
        participant_metrics = self._calculate_participants(issue, comments)
        reopen_metrics = self._calculate_reopen_metrics(issue, timeline)
        
        # Find closing PR or commit
        closing_pr = None
        closing_commit = None
        
        if issue.state == "closed":
            closing_pr, closing_commit = self._find_closing_method(
                owner, repo, number,
                issue.created_at.isoformat() if issue.created_at else None,
                issue.closed_at.isoformat() if issue.closed_at else None,
                timeline
            )
        
        # Format comments as markdown transcript and text
        comments_md = self._build_comments_markdown(comments_data)
        comments_text = self._build_comments_text(comments_data)
        
        # Extract labels
        labels = [
            {
                "name": label.name,
                "description": label.description if hasattr(label, 'description') else None,
                "color": label.color
            }
            for label in issue.labels
        ]
        
        # Extract assignees
        assignees = [
            {
                "username": user.login,
                "id": user.id
            }
            for user in issue.assignees
        ]
        
        # Extract milestone
        milestone = None
        if issue.milestone:
            milestone = {
                "number": issue.milestone.number,
                "title": issue.milestone.title,
                "state": issue.milestone.state,
                "due_on": issue.milestone.due_on.isoformat() if issue.milestone.due_on else None
            }
        
        return {
            # Basic info
            "owner": owner,
            "repo": repo,
            "number": issue.number,
            "id": issue.id,
            "url": issue.html_url,
            "title": issue.title,
            "body": issue.body or "",
            
            # State
            "state": issue.state,
            "state_reason": issue.raw_data.get("state_reason"),
            "locked": issue.locked,
            
            # Timestamps
            "created_at": issue.created_at.isoformat() if issue.created_at else None,
            "updated_at": issue.updated_at.isoformat() if issue.updated_at else None,
            "closed_at": issue.closed_at.isoformat() if issue.closed_at else None,
            
            # Metrics
            "timestamp_metrics": timestamp_metrics,
            "participant_metrics": participant_metrics,
            "reopen_metrics": reopen_metrics,
            
            # Author
            "author": {
                "username": issue.user.login if issue.user else None,
                "id": issue.user.id if issue.user else None,
                "author_association": issue.raw_data.get("author_association")
            },
            
            # Closed by
            "closed_by": {
                "username": issue.closed_by.login if issue.closed_by else None,
                "id": issue.closed_by.id if issue.closed_by else None
            } if issue.closed_by else None,
            
            # Labels, assignees, milestone
            "labels": labels,
            "assignees": assignees,
            "milestone": milestone,
            
            # Comments
            "comments_count": issue.comments,
            "comments": comments_data,
            "comments_md": comments_md,
            "comments_text": comments_text,
            "maintainer_comments": maintainer_comments,
            
            # Closing method
            "closing_pr": closing_pr,
            "closing_commit": closing_commit,
        }
    
    def _calculate_timestamps(self, issue, comments):
        """Calculate timestamp-based metrics"""
        created_at = issue.created_at
        closed_at = issue.closed_at
        
        metrics = {
            "time_to_close_seconds": None,
            "time_to_first_response_seconds": None,
            "time_open_seconds": None
        }
        
        # Time to close
        if created_at and closed_at:
            metrics["time_to_close_seconds"] = int((closed_at - created_at).total_seconds())
        
        # Time to first response
        if created_at and comments:
            first_comment = min(comments, key=lambda c: c.get("created_at", "9999"))
            first_comment_time = self._parse_timestamp(first_comment.get("created_at"))
            if first_comment_time:
                # Make timezone-aware if needed
                if created_at.tzinfo and not first_comment_time.tzinfo:
                    from datetime import timezone
                    first_comment_time = first_comment_time.replace(tzinfo=timezone.utc)
                elif not created_at.tzinfo and first_comment_time.tzinfo:
                    created_at = created_at.replace(tzinfo=timezone.utc)
                
                metrics["time_to_first_response_seconds"] = int((first_comment_time - created_at).total_seconds())
        
        # Time open (from creation to now if still open, or to close if closed)
        if created_at:
            from datetime import timezone
            end_time = closed_at if closed_at else datetime.now(timezone.utc)
            
            # Ensure both are timezone-aware
            if not created_at.tzinfo:
                created_at = created_at.replace(tzinfo=timezone.utc)
            
            metrics["time_open_seconds"] = int((end_time - created_at).total_seconds())
        
        return metrics
        
    def _calculate_participants(self, issue, comments):
        """Calculate participant-based metrics"""
        participants = set()
        maintainers = set()
        
        # Add issue author
        if issue.user:
            participants.add(issue.user.login)
        
        # Add commenters
        for comment in comments:
            username = comment.get("user", {}).get("login")
            assoc = comment.get("author_association", "")
            
            if username:
                participants.add(username)
                
                if assoc in ["OWNER", "MEMBER", "COLLABORATOR"]:
                    maintainers.add(username)
        
        return {
            "unique_participants": len(participants),
            "unique_maintainers": len(maintainers),
            "maintainer_involved": len(maintainers) > 0
        }
    
    def _calculate_reopen_metrics(self, issue, events):
        """Calculate metrics related to issue reopening"""
        metrics = {
            "was_reopened": False,
            "reopen_count": 0,
            "time_to_reopen_seconds": None,
            "final_resolution_time_seconds": None,
            "reopen_timestamps": []
        }
        
        # Find all closed and reopened events
        closed_events = [e for e in events if e.get("event") == "closed"]
        reopened_events = [e for e in events if e.get("event") == "reopened"]
        
        if not reopened_events:
            return metrics
        
        # Issue was reopened at least once
        metrics["was_reopened"] = True
        metrics["reopen_count"] = len(reopened_events)
        metrics["reopen_timestamps"] = [e.get("created_at") for e in reopened_events]
        
        # Time to first reopen
        if closed_events and reopened_events:
            first_close = min(closed_events, key=lambda e: e.get("created_at", ""))
            first_reopen = min(reopened_events, key=lambda e: e.get("created_at", ""))
            
            first_close_time = self._parse_timestamp(first_close.get("created_at"))
            first_reopen_time = self._parse_timestamp(first_reopen.get("created_at"))
            
            if first_close_time and first_reopen_time:
                metrics["time_to_reopen_seconds"] = int((first_reopen_time - first_close_time).total_seconds())
        
        # Final resolution time
        if issue.state == "closed" and issue.created_at and issue.closed_at:
            metrics["final_resolution_time_seconds"] = int((issue.closed_at - issue.created_at).total_seconds())
        
        return metrics
    
    def _fetch_comments(self, owner, repo, number):
        """Fetch all comments via REST API"""
        url = f"https://api.github.com/repos/{owner}/{repo}/issues/{number}/comments"
        return self._fetch_paginated(url)
    
    def _fetch_timeline(self, owner, repo, number):
        """Fetch timeline events"""
        url = f"https://api.github.com/repos/{owner}/{repo}/issues/{number}/timeline"
        
        try:
            timeline_headers = self.headers.copy()
            timeline_headers["Accept"] = "application/vnd.github.mockingbird-preview+json"
            
            items = []
            page = 1
            while True:
                r = requests.get(f"{url}?per_page=100&page={page}", headers=timeline_headers)
                
                # Handle rate limiting
                if r.status_code == 403 and r.headers.get("X-RateLimit-Remaining") == "0":
                    reset = int(r.headers.get("X-RateLimit-Reset", 0))
                    sleep_time = max(0, reset - int(time.time()) + 1)
                    print(f"   Rate limited, sleeping {sleep_time}s...")
                    time.sleep(sleep_time)
                    continue
                
                r.raise_for_status()
                data = r.json()
                
                if not data:
                    break
                
                items.extend(data)
                
                if len(data) < 100:
                    break
                
                page += 1
            
            return items
        except Exception as e:
            print(f"   Could not fetch timeline: {e}")
            return []
    
    def _fetch_paginated(self, url):
        """Fetch all pages of data"""
        items = []
        page = 1
        
        while True:
            r = requests.get(f"{url}?per_page=100&page={page}", headers=self.headers)
            
            # Handle rate limiting
            if r.status_code == 403 and r.headers.get("X-RateLimit-Remaining") == "0":
                reset = int(r.headers.get("X-RateLimit-Reset", 0))
                sleep_time = max(0, reset - int(time.time()) + 1)
                print(f"   Rate limited, sleeping {sleep_time}s...")
                time.sleep(sleep_time)
                continue
            
            r.raise_for_status()
            data = r.json()
            
            if not data:
                break
            
            items.extend(data)
            
            if len(data) < 100:
                break
            
            page += 1
        
        return items
    
    def _find_closing_method(self, owner, repo, number, created_at, closed_at, events):
        """Find if issue was closed by PR or direct commit"""
        
        # Parse timestamps for validation
        issue_created_time = self._parse_timestamp(created_at)
        issue_closed_time = self._parse_timestamp(closed_at)
        
        # Look for "closed" event with commit_id or pull_request
        for event in reversed(events):  # Start from most recent
            if event.get("event") == "closed":
                # Check if closed by PR
                if event.get("commit_id"):
                    commit_sha = event["commit_id"]
                    
                    # Check if this commit is part of a PR
                    try:
                        url = f"https://api.github.com/repos/{owner}/{repo}/commits/{commit_sha}/pulls"
                        prs = self._fetch(url)
                        
                        if prs:
                            pr_number = prs[0].get("number")
                            print(f"      Closed by PR #{pr_number}, fetching details...")
                            pr_details = self._fetch_pr_details(owner, repo, pr_number)
                            
                            # Validate PR timing
                            if pr_details and pr_details.get("merged"):
                                pr_merged_time = self._parse_timestamp(pr_details.get("merged_at"))
                                
                                if pr_merged_time and issue_created_time and issue_closed_time:
                                    # Check if merged after issue creation
                                    if pr_merged_time < issue_created_time:
                                        print(f"      PR #{pr_number} was merged before issue was created, ignoring")
                                        continue
                                    
                                    # Check if merged within 7 days of issue closing
                                    time_diff = abs((pr_merged_time - issue_closed_time).total_seconds())
                                    if time_diff > 604800:  # 7 days in seconds
                                        print(f"      PR #{pr_number} was merged too far from close time ({time_diff/86400:.1f} days), ignoring")
                                        continue
                            
                            return pr_details, None
                        else:
                            # Direct commit
                            print(f"      Closed by commit {commit_sha[:7]}, fetching details...")
                            commit_details = self._fetch_commit_details(owner, repo, commit_sha)
                            return None, commit_details
                    except Exception as e:
                        print(f"      Could not determine closing method: {e}")
                        continue
        
        return None, None
    
    def _fetch_pr_details(self, owner, repo, pr_number):
        """Fetch detailed PR information with all metrics"""
        url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}"
        
        try:
            pr = self._fetch(url)
            
            # Fetch PR reviews
            reviews = self._fetch_pr_reviews(owner, repo, pr_number)
            
            # Count unique reviewers and review states
            reviewers = set()
            review_states = {
                "approved": 0,
                "changes_requested": 0,
                "commented": 0,
                "dismissed": 0
            }
            
            for review in reviews:
                reviewer_username = review.get("user", {}).get("login")
                if reviewer_username:
                    reviewers.add(reviewer_username)
                
                state = review.get("state", "").lower()
                if state in review_states:
                    review_states[state] += 1
            
            # Extract author and merger info
            pr_author = pr.get("user") or {}
            merged_by = pr.get("merged_by") or {}
            
            return {
                "number": pr.get("number"),
                "title": pr.get("title"),
                "html_url": pr.get("html_url"),
                "merged": bool(pr.get("merged_at")),
                "merged_at": pr.get("merged_at"),
                "created_at": pr.get("created_at"),
                "updated_at": pr.get("updated_at"),
                "closed_at": pr.get("closed_at"),
                "state": pr.get("state"),
                "body": pr.get("body"),
                
                # Author info
                "author": {
                    "username": pr_author.get("login"),
                    "id": pr_author.get("id"),
                    "name": pr_author.get("name"),
                    "email": pr_author.get("email")
                },
                
                # Merger info
                "merged_by": {
                    "username": merged_by.get("login"),
                    "id": merged_by.get("id"),
                    "name": merged_by.get("name"),
                    "email": merged_by.get("email")
                } if merged_by else None,
                
                # Code changes
                "commits": pr.get("commits"),
                "additions": pr.get("additions"),
                "deletions": pr.get("deletions"),
                "total_changes": (pr.get("additions") or 0) + (pr.get("deletions") or 0),
                "changed_files": pr.get("changed_files"),
                "files_changed": pr.get("changed_files"),
                
                # Review info
                "review_comments": pr.get("review_comments"),
                "comments": pr.get("comments"),
                "unique_reviewers": len(reviewers),
                "reviewer_usernames": sorted(list(reviewers)),
                "total_reviews": len(reviews),
                "approved_count": review_states["approved"],
                "changes_requested_count": review_states["changes_requested"],
                "commented_count": review_states["commented"],
                
                # Branch info
                "head_ref": pr.get("head", {}).get("ref"),
                "base_ref": pr.get("base", {}).get("ref"),
                "head_sha": pr.get("head", {}).get("sha"),
                "merge_commit_sha": pr.get("merge_commit_sha")
            }
        except Exception as e:
            print(f"      Error fetching PR details: {e}")
            return None
        
    def _fetch_pr_reviews(self, owner, repo, pr_number):
        """Fetch all reviews for a PR"""
        url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}/reviews"
        
        try:
            return self._fetch_paginated(url)
        except Exception as e:
            print(f"      Could not fetch PR reviews: {e}")
            return []
    
    def _fetch_commit_details(self, owner, repo, commit_sha):
        """Fetch commit information with all metrics"""
        url = f"https://api.github.com/repos/{owner}/{repo}/commits/{commit_sha}"
        
        try:
            commit = self._fetch(url)
            
            stats = commit.get("stats", {})
            author = commit.get("commit", {}).get("author", {})
            committer = commit.get("commit", {}).get("committer", {})
            
            return {
                "sha": commit.get("sha"),
                "message": commit.get("commit", {}).get("message"),
                "html_url": commit.get("html_url"),
                
                # Author info (git author)
                "author": {
                    "name": author.get("name"),
                    "email": author.get("email"),
                    "date": author.get("date")
                },
                
                # Committer info (git committer)
                "committer": {
                    "name": committer.get("name"),
                    "email": committer.get("email"),
                    "date": committer.get("date")
                },
                
                # GitHub user who authored the commit
                "github_author": {
                    "username": commit.get("author", {}).get("login"),
                    "id": commit.get("author", {}).get("id")
                } if commit.get("author") else None,
                
                # GitHub user who committed
                "github_committer": {
                    "username": commit.get("committer", {}).get("login"),
                    "id": commit.get("committer", {}).get("id")
                } if commit.get("committer") else None,
                
                # Stats
                "additions": stats.get("additions"),
                "deletions": stats.get("deletions"),
                "total_changes": stats.get("total"),
                
                # Files changed (limit to first 20)
                "changed_files": len(commit.get("files", [])),
                "files": [
                    {
                        "filename": f.get("filename"),
                        "status": f.get("status"),
                        "additions": f.get("additions"),
                        "deletions": f.get("deletions"),
                        "changes": f.get("changes")
                    }
                    for f in commit.get("files", [])[:20]
                ]
            }
        except Exception as e:
            print(f"      Error fetching commit details: {e}")
            return None
    
    def _fetch(self, url):
        """Fetch with rate limit handling"""
        while True:
            r = requests.get(url, headers=self.headers)
            
            if r.status_code == 403 and r.headers.get("X-RateLimit-Remaining") == "0":
                reset = int(r.headers.get("X-RateLimit-Reset", 0))
                sleep_time = max(0, reset - int(time.time()) + 1)
                print(f"   Rate limited, sleeping {sleep_time}s...")
                time.sleep(sleep_time)
                continue
            
            r.raise_for_status()
            return r.json()
    
    def _build_comments_markdown(self, comments):
        """Build markdown transcript of comments"""
        if not comments:
            return ""
        
        blocks = []
        for comment in sorted(comments, key=lambda c: c.get("created_at", "")):
            timestamp = comment.get("created_at", "Unknown")
            author = comment.get("author", {})
            username = author.get("username", "unknown")
            assoc = author.get("author_association", "NONE")
            body = comment.get("body", "")
            
            blocks.append(f"[{timestamp}] [{assoc}] {username}:\n{body}")
        
        return "\n\n---\n\n".join(blocks)
    
    def _build_comments_text(self, comments):
        """Build plain text transcript of comments"""
        if not comments:
            return ""
        
        blocks = []
        for comment in sorted(comments, key=lambda c: c.get("created_at", "")):
            timestamp = comment.get("created_at", "Unknown")
            author = comment.get("author", {})
            username = author.get("username", "unknown")
            assoc = author.get("author_association", "NONE")
            body = comment.get("body", "")
            
            # Format timestamp
            ts_obj = self._parse_timestamp(timestamp)
            if ts_obj:
                ts_str = ts_obj.strftime("%Y-%m-%d %H:%MZ")
            else:
                ts_str = "0000-00-00 00:00Z"
            
            blocks.append(f"[{ts_str}] [{assoc}] {username}:\n{body}")
        
        return "\n\n---\n\n".join(blocks)
    
    def _parse_timestamp(self, iso_string):
        """Convert ISO timestamp string to datetime object"""
        if not iso_string:
            return None
        try:
            return datetime.fromisoformat(iso_string.replace("Z", "+00:00"))
        except:
            return None