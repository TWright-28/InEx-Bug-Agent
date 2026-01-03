from tools.collector import IssueCollector
from dotenv import load_dotenv

load_dotenv()

# Create collector
collector = IssueCollector()

# Test with a real repo (just 3 issues)
issues = collector.collect('facebook/react', limit=3)

# Print results
for issue in issues:
    print(f"\n#{issue['number']}: {issue['title']}")
    print(f"State: {issue['state']}")
    print(f"URL: {issue['url']}")