import requests
import re
import os

class BugClassifier:
    def __init__(self, model_url="http://localhost:11434", model_name="gpt-oss:20b"):        
        self.model_url = model_url
        self.model_name = model_name
        self.classification_prompt = self._load_prompt()
    
    def _load_prompt(self):
        """Load the classification guide from file"""
        prompt_file = "classification_prompt.txt"
        
        if not os.path.exists(prompt_file):
            raise FileNotFoundError(f"{prompt_file} not found. Please create it with your classification guide.")
        
        with open(prompt_file, 'r', encoding='utf-8') as f:
            return f.read()
    
    def classify(self, issue_data):
        """Classify a single issue"""
        
        # Build the full prompt
        prompt = self._build_prompt(issue_data)
        
        # Call Ollama
        try:
            response = self._call_ollama(prompt)
            
            return {
                'classification': self._parse_classification(response),
                'reasoning': self._extract_reasoning(response),
                'probabilities': self._extract_probabilities(response),
                'raw_response': response
            }
        except Exception as e:
            print(f"Error: {e}")
            return {
                'classification': 'UNKNOWN',
                'reasoning': f'Error: {str(e)}',
                'probabilities': {}
            }
    
    def _build_prompt(self, issue_data):
        """Build the complete prompt with issue data"""
        
        # Extract simple fields
        repo = issue_data.get('repo', 'Unknown')
        owner = issue_data.get('owner', 'Unknown')
        full_repo = f"{owner}/{repo}"
        
        # Format labels
        labels = issue_data.get('labels', [])
        if isinstance(labels, list) and labels and isinstance(labels[0], dict):
            labels_str = ', '.join([l.get('name', '') for l in labels])
        elif isinstance(labels, list):
            labels_str = ', '.join(labels)
        else:
            labels_str = 'None'
        
        # Format closing PR details
        closing_pr_section = ""
        if issue_data.get('closing_pr'):
            pr = issue_data['closing_pr']
            closing_pr_section = f"""

    **Closing PR:**
    - Number: #{pr.get('number')}
    - Title: {pr.get('title')}
    - Body: {pr.get('body', '')[:2000]}
    - Merged: {pr.get('merged')}
    - Files Changed: {pr.get('changed_files')}
    - Additions: {pr.get('additions')}
    - Deletions: {pr.get('deletions')}
    """
        
        # Format closing commit details
        closing_commit_section = ""
        if issue_data.get('closing_commit'):
            commit = issue_data['closing_commit']
            closing_commit_section = f"""

    **Closing Commit:**
    - SHA: {commit.get('sha', '')[:7]}
    - Message: {commit.get('message', '')[:500]}
    """
        
        issue_section = f"""

    NOW CLASSIFY THIS ISSUE:

    **Bug Project:** {full_repo}
    **Bug Title:** {issue_data.get('title', 'No title')}
    **Bug Number:** #{issue_data.get('number', 'Unknown')}

    **Bug Description:** 
    {issue_data.get('body', 'No description')[:3000]}

    **Labels:** {labels_str}
    **State:** {issue_data.get('state', 'unknown')}
    **Created:** {issue_data.get('created_at', 'Unknown')}
    **Closed:** {issue_data.get('closed_at', 'Not closed')}

    **Author:** {issue_data.get('author', {}).get('username', 'Unknown')} (Role: {issue_data.get('author', {}).get('author_association', 'NONE')})
    {closing_pr_section}{closing_commit_section}

    **Comments (Discussion):**
    {issue_data.get('comments_md', 'No comments')[:4000]}

    ---

    Please analyze this issue using the framework provided.
    """
        
        return self.classification_prompt + "\n\n" + issue_section
    
    def _call_ollama(self, prompt):
        """Call Ollama API"""
        
        response = requests.post(
            f"{self.model_url}/api/generate",
            json={
                'model': self.model_name,
                'prompt': prompt,
                'temperature': 0.2,
                'stream': False,
                'options': {
                    'num_predict': 32000,
                }
            },
            timeout=300  # 5 minute timeout for long responses
        )
        
        if response.status_code == 200:
            return response.json()['response']
        else:
            raise Exception(f"Ollama API error: {response.status_code}")
    
    def _parse_classification(self, response):
        """Extract the final classification"""
        
        # Look for "**Final Answer:** [CATEGORY]"
        pattern = r"\*\*Final Answer:\*\*\s*(Intrinsic|Extrinsic|Not a Bug|Unknown)"
        match = re.search(pattern, response, re.IGNORECASE)
        
        if match:
            answer = match.group(1)
            if answer.lower() == 'not a bug':
                return 'NOT_A_BUG'
            return answer.upper()
        
        # Fallback
        for label in ['INTRINSIC', 'EXTRINSIC', 'NOT_A_BUG', 'UNKNOWN']:
            if label.lower() in response.lower():
                return label
        
        return 'UNKNOWN'
    
    def _extract_reasoning(self, response):
        """Extract the reasoning section"""
        
        lines = response.split('\n')
        reasoning_lines = []
        in_reasoning = False
        
        for line in lines:
            if 'reasoning:' in line.lower() or '**reasoning:**' in line.lower():
                in_reasoning = True
                continue
            
            if in_reasoning:
                if '**final answer:**' in line.lower() or 'probability distribution' in line.lower():
                    break
                reasoning_lines.append(line)
        
        reasoning = '\n'.join(reasoning_lines).strip()
        
        if not reasoning:
            try:
                reasoning = response.split('**Final Answer:**')[0].strip()[-1000:]
            except:
                reasoning = response[:1000]
        
        return reasoning
    
    def _extract_probabilities(self, response):
        """Extract probability distribution"""
        
        probabilities = {}
        
        patterns = {
            'INTRINSIC': r'Intrinsic:\s*(0\.\d+)',
            'EXTRINSIC': r'Extrinsic:\s*(0\.\d+)',
            'NOT_A_BUG': r'Not a Bug:\s*(0\.\d+)',
            'UNKNOWN': r'Unknown:\s*(0\.\d+)'
        }
        
        for key, pattern in patterns.items():
            match = re.search(pattern, response, re.IGNORECASE)
            if match:
                probabilities[key] = float(match.group(1))
        
        return probabilities