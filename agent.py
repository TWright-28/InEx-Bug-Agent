from langchain_ollama import OllamaLLM
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough
from tools.collector import IssueCollector
from tools.classifier import BugClassifier
from dotenv import load_dotenv
import re
import json
from datetime import datetime
import os

load_dotenv()

class BugAgent:
    def __init__(self):
        # Create the LLM
        self.llm = OllamaLLM(
            model="gpt-oss:20b",
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
        
        # Prepare results storage
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        results_file = f"data/results_{timestamp}.jsonl"
        log_file = f"data/classification_{timestamp}.log"
        collected_file = f"data/collected_{timestamp}.jsonl"  # NEW: Save collected data
        
        # Ensure data directory exists
        os.makedirs('data', exist_ok=True)
        
        # Save collected issues
        print(f"\nSaving collected issues to {collected_file}...")
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
                
                classification = self.classifier.classify(issue)
                
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

Collected data saved to: {collected_file}
Results saved to: {results_file}
Log saved to: {log_file}
"""
        
        return summary