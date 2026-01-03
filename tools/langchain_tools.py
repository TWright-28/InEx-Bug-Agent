from langchain.tools import Tool
from tools.collector import IssueCollector
from tools.classifier import BugClassifier

def create_tools():
    """Create LangChain tools for the agent"""
    
    collector = IssueCollector()
    classifier = BugClassifier()
    
    def collect_and_classify(input_str):
        """Collect and classify issues from a repository.
        Input should be: repo_name,limit
        Example: facebook/react,10
        """
        try:
            parts = input_str.split(',')
            repo = parts[0].strip()
            limit = int(parts[1].strip()) if len(parts) > 1 else 10
            
            # Collect issues
            issues = collector.collect(repo, limit)
            
            # Classify each
            results = []
            for issue in issues:
                classification = classifier.classify(issue)
                results.append({
                    'number': issue['number'],
                    'title': issue['title'],
                    'classification': classification['classification']
                })
            
            # Return summary
            intrinsic = len([r for r in results if r['classification'] == 'INTRINSIC'])
            extrinsic = len([r for r in results if r['classification'] == 'EXTRINSIC'])
            
            return f"Classified {len(results)} issues: {intrinsic} intrinsic, {extrinsic} extrinsic"
            
        except Exception as e:
            return f"Error: {str(e)}"
    
    tools = [
        Tool(
            name="collect_and_classify",
            func=collect_and_classify,
            description="Collect and classify bug reports from a GitHub repository. Input: 'owner/repo,limit' (e.g., 'facebook/react,10')"
        )
    ]
    
    return tools