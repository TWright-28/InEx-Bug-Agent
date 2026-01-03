from langchain_ollama import OllamaLLM
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough
from tools.collector import IssueCollector
from tools.classifier import BugClassifier
from dotenv import load_dotenv
import re

load_dotenv()

class BugAgent:
    def __init__(self):
        # Create the LLM
        self.llm = OllamaLLM(
            model="gpt-oss-20b",
            base_url="http://localhost:11434",
            temperature=0.2,
            num_predict=32000
        )
        
        # Create tools
        self.collector = IssueCollector()
        self.classifier = BugClassifier()
        
        # Create a simple prompt for the agent
        self.prompt = ChatPromptTemplate.from_messages([
            ("system", "You are a helpful assistant that helps classify bug reports from GitHub repositories."),
            ("human", "{input}")
        ])
        
        # Create chain
        self.chain = self.prompt | self.llm | StrOutputParser()
    
    def chat(self, message):
        """Send a message to the agent"""
        
        # Check if user wants to classify
        if "classify" in message.lower():
            # Extract repo
            repo_match = re.search(r'([a-zA-Z0-9_-]+/[a-zA-Z0-9_-]+)', message)
            
            if repo_match:
                repo = repo_match.group(1)
                
                # Extract number
                num_match = re.search(r'(\d+)', message)
                limit = int(num_match.group(1)) if num_match else 10
                
                # Collect and classify
                return self._classify_repo(repo, limit)
            else:
                return "Please specify a repository in the format: owner/repo"
        
        # Otherwise, just chat with LLM
        response = self.chain.invoke({"input": message})
        return response
    
    def _classify_repo(self, repo, limit):
        """Collect and classify issues from a repo"""
        
        # Collect
        issues = self.collector.collect(repo, limit)
        
        if not issues:
            return f"No issues found in {repo}"
        
        # Classify each
        results = []
        for i, issue in enumerate(issues, 1):
            print(f"  Classifying {i}/{len(issues)}...")
            classification = self.classifier.classify(issue)
            results.append({
                'number': issue['number'],
                'title': issue['title'],
                'classification': classification['classification']
            })
        
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
"""
        
        return summary