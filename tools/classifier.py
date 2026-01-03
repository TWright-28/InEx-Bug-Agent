import requests

class BugClassifier:
    def __init__(self, model_url="http://localhost:11434", model_name="gpt-oss-120b"):
        self.model_url = model_url
        self.model_name = model_name
    
    def classify(self, issue_data):
        """Classify a single issue"""
        
        # For now, just a simple test
        print(f"Classifying issue: {issue_data.get('title', 'Unknown')}")
        
        return {
            'classification': 'INTRINSIC',
            'reasoning': 'Test classification'
        }