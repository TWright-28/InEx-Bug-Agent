from langchain_ollama import ChatOllama
from langchain.agents import AgentExecutor, create_react_agent
from langchain_core.prompts import PromptTemplate
from langchain.memory import ConversationBufferMemory
from tools.langchain_tools import create_tools
from dotenv import load_dotenv
import os
from datetime import datetime
import io
import sys

load_dotenv()

class BugAgent:
    def __init__(self):
        self.llm = ChatOllama(
            model="qwen3:30b",
            base_url="http://localhost:11434",
            temperature=0.3,
            num_predict=4096
        )
        
        self.tools = create_tools()
        
        template = """You are a helpful bug classification assistant for GitHub issues.

AVAILABLE TOOLS:
{tools}

Tool names: {tool_names}

═══════════════════════════════════════════════════════════════════
TOOL DESCRIPTIONS
═══════════════════════════════════════════════════════════════════

1. list_repositories: Browse GitHub repos for a user/org
2. collect_bugs: Fetch issues from GitHub (NO classification)
3. classify_bugs: Fetch issues AND classify them
4. classify_from_file: Classify previously collected issues
5. merge_classifications: Combine collected + classified data
6. analyze_classifications: Generate statistics and figures

═══════════════════════════════════════════════════════════════════
WORKFLOW PATTERNS
═══════════════════════════════════════════════════════════════════

PATTERN 1: Collect Only
User: "collect 5 bugs from react"
→ Action: collect_bugs → Done

PATTERN 2: Classify (new collection)
User: "classify 5 bugs from react"
→ Action: classify_bugs → Done

PATTERN 3: Classify (existing collection)
User: [after collecting] "classify them"
→ Action: classify_from_file → Done

PATTERN 4: Full Analysis Workflow
User: "classify 5 bugs and analyze"
→ Step 1: classify_bugs
→ Step 2: merge_classifications
→ Step 3: analyze_classifications
→ Done

═══════════════════════════════════════════════════════════════════
CRITICAL RULES
═══════════════════════════════════════════════════════════════════

RULE 1: ONE TOOL CALL PER THOUGHT
After calling a tool, WAIT for the Observation before deciding next action.

RULE 2: NO REPEATED CALLS
If a tool returns a success message, it worked.
DO NOT call it again with the same input.
Check the Observation for "saved to" or "complete" - if present, move on.

RULE 3: MERGE → ANALYZE SEQUENCE
After merge_classifications succeeds (shows "Output saved to"), 
the ONLY valid next action is analyze_classifications.
DO NOT call merge again!

RULE 4: RESPECT USER INTENT
- If user says "collect" → collect_bugs only
- If user says "classify" → classify_bugs only (don't auto-analyze)
- If user says "analyze" → do full workflow (classify → merge → analyze)

═══════════════════════════════════════════════════════════════════
SUCCESS INDICATORS
═══════════════════════════════════════════════════════════════════

After calling a tool, check the Observation for these success messages:

- collect_bugs: "Data collected successfully"
- classify_bugs: "Results saved to: data/results_"
- classify_from_file: "Results saved to: data/results_"
- merge_classifications: "Output saved to: issues_with_classifications.jsonl"
- analyze_classifications: "Analysis complete!"

If you see the SUCCESS indicator, that tool is DONE.
Move to next step OR give Final Answer.
DO NOT call the same tool again!

═══════════════════════════════════════════════════════════════════
RESPONSE FORMAT
═══════════════════════════════════════════════════════════════════

Always use this exact format:

Thought: [What I need to do]
Action: [tool name]
Action Input: [tool input]

[WAIT FOR OBSERVATION]

Thought: [What the observation tells me]
Action: [next tool if needed] OR Final Answer: [if done]

═══════════════════════════════════════════════════════════════════
EXAMPLES
═══════════════════════════════════════════════════════════════════

Example 1: Collect only
User: "collect 2 bugs from numpy"
Thought: User wants to collect bugs without classification
Action: collect_bugs
Action Input: numpy/numpy,2
Observation: Collected 2 issues... saved to data/collected_X.jsonl
Thought: Collection complete, user didn't ask for classification
Final Answer: Collected 2 bugs from numpy. Saved to data/collected_X.jsonl

Example 2: Classify existing bugs
User: "classify them"
Thought: User wants to classify previously collected bugs
Action: classify_from_file
Action Input: data/collected_20260112_154725.jsonl
Observation: Classification complete... saved to data/results_X.jsonl
Thought: Classification done, user didn't ask for analysis
Final Answer: Classified 2 bugs. Results in data/results_X.jsonl

Example 3: Analyze workflow
User: "analyze them"
Thought: User wants analysis, need to merge first
Action: merge_classifications
Action Input: data/collected_X.jsonl,data/results_Y.jsonl
Observation: Successfully merged... Output saved to: issues_with_classifications.jsonl
Thought: Merge succeeded, now I must analyze (NOT merge again)
Action: analyze_classifications
Action Input: issues_with_classifications.jsonl
Observation: Analysis complete! Generated figures/...
Thought: Analysis done
Final Answer: Analysis complete! Generated comprehensive_analysis.png, ...

═══════════════════════════════════════════════════════════════════

Previous conversation:
{chat_history}

Current request:
{input}

{agent_scratchpad}"""

        prompt = PromptTemplate.from_template(template)
        
        self.memory = ConversationBufferMemory(
            memory_key="chat_history",
            return_messages=False
        )
        
        agent = create_react_agent(
            llm=self.llm,
            tools=self.tools,
            prompt=prompt
        )
        
        self.agent_executor = AgentExecutor(
            agent=agent,
            tools=self.tools,
            memory=self.memory,
            verbose=True,
            handle_parsing_errors=True,
            max_iterations=5,  # Reduced from 7 to prevent long loops
            return_intermediate_steps=True
        )
    
    def chat(self, message):
        """Handle user message and log session"""
        os.makedirs('logs', exist_ok=True)
        
        if not hasattr(self, 'session_log'):
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            self.session_log = f"logs/agent_session_{timestamp}.log"
        
        try:
            # Capture agent thinking
            old_stdout = sys.stdout
            sys.stdout = captured_output = io.StringIO()
            
            # Log user input
            with open(self.session_log, 'a', encoding='utf-8') as f:
                f.write(f"\n{'='*80}\n")
                f.write(f"User: {message}\n")
                f.write(f"Timestamp: {datetime.now().isoformat()}\n")
                f.write(f"{'='*80}\n\n")
            
            # Run agent
            response = self.agent_executor.invoke({"input": message})
            
            # Restore stdout
            sys.stdout = old_stdout
            
            # Get thinking process
            agent_thinking = captured_output.getvalue()
            
            # Print to console
            print(agent_thinking)
            
            # Log everything
            with open(self.session_log, 'a', encoding='utf-8') as f:
                f.write("Agent Thinking:\n")
                f.write(agent_thinking)
                f.write(f"\n\nFinal Response:\n")
                f.write(f"{response.get('output', 'No response')}\n")
                f.write(f"\n{'='*80}\n")
            
            print(f"\nSession logged to: {self.session_log}")
            
            return response.get("output", "I'm not sure how to respond to that.")
            
        except Exception as e:
            sys.stdout = old_stdout
            
            with open(self.session_log, 'a', encoding='utf-8') as f:
                f.write(f"\nERROR: {str(e)}\n")
                f.write(f"\n{'='*80}\n")
            
            print(f"Error: {e}")
            return f"Sorry, I encountered an error: {str(e)}"