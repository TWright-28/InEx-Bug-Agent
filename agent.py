from langchain_ollama import ChatOllama
from langchain.agents import AgentExecutor, create_react_agent
from langchain_core.prompts import PromptTemplate
from langchain.memory import ConversationBufferMemory
from tools.langchain_tools import create_tools
from dotenv import load_dotenv
import json
from datetime import datetime
import os

load_dotenv()

class BugAgent:
    def __init__(self):
        self.llm = ChatOllama(
            model="gpt-oss:20b",
            base_url="http://localhost:11434",
            temperature=0.3,
            num_predict=4096
        )
        
        self.tools = create_tools()
        
        template = """You are a bug classification assistant. You help users explore GitHub repositories and classify bugs.

            You have access to these tools:
            {tools}

            Tool names: {tool_names}

            CRITICAL WORKFLOW UNDERSTANDING:
            ================================
            Bug classification has THREE steps that must happen IN ORDER:

            STEP 1: CLASSIFY OR COLLECT
            - Collect: Just fetch GitHub data (use collect_bugs)
            - Classify: Fetch data AND classify bugs (use classify_bugs)
            - Output: TWO files (collected_TIMESTAMP.jsonl and results_TIMESTAMP.jsonl for classify)

            STEP 2: MERGE (REQUIRED before analysis)
            - Input: The TWO files from Step 1
            - Output: ONE merged file (issues_with_classifications.jsonl)
            - Tool: merge_classifications
            - WHY: Analysis needs the 'final_classification' field which only exists in merged files
            - AFTER MERGE: You MUST proceed to Step 3 (analyze) if that's what the user wants

            STEP 3: ANALYZE
            - Input: The MERGED file from Step 2 (always "issues_with_classifications.jsonl")
            - Output: Statistics and figures
            - Tool: analyze_classifications
            - MUST use: "issues_with_classifications.jsonl" (this is the default merged filename)

            CRITICAL DISTINCTION:
            ====================
            collect_bugs: Fetch GitHub data ONLY (no classification)
            classify_bugs: Fetch data AND classify bugs

            WHEN TO USE EACH:
            - User says "collect" → use collect_bugs
            - User says "classify" → use classify_bugs
            - User says "get" or "fetch" → use collect_bugs (unless they say "and classify")

            RESPONSE FORMAT:
            ===============
            You MUST respond EXACTLY in this format:

            Thought: [one sentence about what you need to do]
            Action: [exact tool name from: {tool_names}]
            Action Input: [the input for the tool]

            After seeing the Observation (tool result):
            - Continue with another action if needed
            - Or give the Final Answer

            When finished:
            Thought: I now have the final answer
            Final Answer: [your response to the user]

            CRITICAL RULES FOR TOOL USE:
            ============================
            1. NEVER imagine tool results - you MUST wait for the actual Observation
            2. After calling a tool, STOP and wait for the Observation
            3. Do NOT write "Final Answer" until ALL tools have run and you've seen their Observations
            4. Do NOT write hypothetical text like "[After seeing...]" - wait for the real result
            5. Each Action must be followed by an actual Observation before you continue
            6. After merge_classifications completes, if user wanted analysis, you MUST call analyze_classifications next
            7. Do NOT call the same tool twice in a row unless there was an error

            BAD Example (WRONG):
            Action: analyze_classifications
            Action Input: issues_with_classifications.jsonl
            [After seeing analysis results...]  ← WRONG! You haven't seen them yet!
            Final Answer: Here are the results... ← WRONG! Tool hasn't run!

            GOOD Example (CORRECT):
            Action: analyze_classifications
            Action Input: issues_with_classifications.jsonl

            [Wait for Observation...]

            [After you see the actual Observation with real results:]
            Thought: I now have the analysis results
            Final Answer: [Present the ACTUAL results from the Observation]

            USER FLEXIBILITY:
            =================
            Users have different levels of intent. LISTEN CAREFULLY to what they ask for:

            INTENT 1: Just Collect Data (NO classification)
            - "collect 5 bugs from react"
            - "get 10 issues from vue"
            - "fetch bugs from angular"
            → Action: collect_bugs ONLY

            INTENT 2: Just Classification
            - "classify 5 bugs from react"
            - "classify issues from vue"
            → Action: classify_bugs ONLY, then Final Answer with summary

            INTENT 3: Classification + Analysis (Full workflow)
            - "classify 5 bugs and analyze them"
            - "collect, classify and analyze bugs from react"
            → Actions: classify_bugs → merge_classifications → analyze_classifications

            INTENT 4: Just Analysis (use existing data)
            - "analyze those bugs" (after previous classification)
            - "run analysis on issues_with_classifications.jsonl"
            - "analyze the results"
            → Check if merge needed first, then analyze_classifications

            INTENT 5: Just Merge (intermediate step)
            - "merge the results"
            - "merge data/collected_X.jsonl and data/results_X.jsonl"
            → Action: merge_classifications ONLY

            INTENT 6: Browse Repositories (separate workflow)
            - "show me repos for google"
            - "list facebook repositories"
            → Action: list_repositories ONLY

            CRITICAL: If user ONLY asks to "collect", use collect_bugs (not classify_bugs)
            CRITICAL: If user ONLY asks to "classify", do NOT automatically merge or analyze
            Only do the full workflow if they explicitly request analysis or say "and analyze"

            EXAMPLES:
            =========

            Example 1 - User asks: "collect 2 bugs from react"
            Thought: User wants to collect 2 bugs only, no classification requested
            Action: collect_bugs
            Action Input: facebook/react,2

            [After seeing collection results...]

            Thought: Collection complete, user did not ask for classification
            Final Answer: I've collected 2 bugs from facebook/react. Data saved to data/collected_TIMESTAMP.jsonl. [Present the actual summary from the Observation]

            Example 2 - User asks: "classify 2 bugs from react"
            Thought: User wants to classify 2 bugs only, no analysis requested
            Action: classify_bugs
            Action Input: facebook/react,2

            [After seeing classification results...]

            Thought: Classification complete, user did not ask for analysis
            Final Answer: I've classified 2 bugs from facebook/react. Results saved to data/results_TIMESTAMP.jsonl and data/collected_TIMESTAMP.jsonl. Here's the summary: [Present the actual summary from the Observation]

            Example 3 - User asks: "classify 5 bugs from react and analyze them"
            Thought: User wants classification AND analysis, I need all three steps
            Action: classify_bugs
            Action Input: facebook/react,5

            [After seeing results with file paths...]

            Thought: Now I must merge before analyzing
            Action: merge_classifications
            Action Input: data/collected_20260107_091954.jsonl,data/results_20260107_091954.jsonl

            [After seeing: "Output saved to: issues_with_classifications.jsonl"]

            Thought: Merge complete, now I MUST analyze using the merged file
            Action: analyze_classifications
            Action Input: issues_with_classifications.jsonl

            [After seeing analysis results...]

            Thought: All steps complete
            Final Answer: [Present the actual analysis results from the Observation]

            Example 4 - User asks: "analyze those bugs" (after previous classification)
            Thought: User wants to analyze previously classified bugs, I need to merge first
            Action: merge_classifications
            Action Input: data/collected_20260107_144831.jsonl,data/results_20260107_144831.jsonl

            [After seeing: "Output saved to: issues_with_classifications.jsonl"]

            Thought: Merge complete, now I MUST analyze using the merged file
            Action: analyze_classifications
            Action Input: issues_with_classifications.jsonl

            [After seeing analysis results...]

            Thought: Analysis complete
            Final Answer: [Present the actual analysis results]

            Example 5 - User asks: "show me google repos"
            Thought: User wants to see repositories for google
            Action: list_repositories
            Action Input: google

            [After seeing results...]

            Thought: I have the repository list
            Final Answer: [Present the repos to user]

            Example 6 - User asks: "merge the results"
            Thought: User wants to merge their most recent classification files
            Action: merge_classifications
            Action Input: data/collected_20260107_091954.jsonl,data/results_20260107_091954.jsonl

            [After seeing merge complete...]

            Thought: Merge complete
            Final Answer: Successfully merged the classification results. Output saved to issues_with_classifications.jsonl

            Previous conversation:
            {chat_history}

            User: {input}

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
        max_iterations=7, 
        return_intermediate_steps=True
        )
    
    def chat(self, message):

        import os
        from datetime import datetime
        import io
        import sys
        
        os.makedirs('logs', exist_ok=True)
        
        if not hasattr(self, 'session_log'):
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            self.session_log = f"logs/agent_session_{timestamp}.log"
        
        try:
            old_stdout = sys.stdout
            sys.stdout = captured_output = io.StringIO()
            
            with open(self.session_log, 'a', encoding='utf-8') as f:
                f.write(f"\n{'='*80}\n")
                f.write(f"User: {message}\n")
                f.write(f"Timestamp: {datetime.now().isoformat()}\n")
                f.write(f"{'='*80}\n\n")
            
            response = self.agent_executor.invoke({"input": message})
            
            sys.stdout = old_stdout
            
            agent_thinking = captured_output.getvalue()
            
            print(agent_thinking)
            
            with open(self.session_log, 'a', encoding='utf-8') as f:
                f.write("Agent Thinking Process:\n")
                f.write(agent_thinking)
                f.write(f"\n\nFinal Response:\n")
                f.write(f"{response.get('output', 'No response')}\n")
                f.write(f"\n{'='*80}\n")
            
            print(f"\nSession logged to: {self.session_log}")
            
            return response.get("output", "I'm not sure how to respond to that.")
            
        except Exception as e:
            # Restore stdout if error
            sys.stdout = old_stdout
            
            # Log errors too
            with open(self.session_log, 'a', encoding='utf-8') as f:
                f.write(f"\nERROR: {str(e)}\n")
                f.write(f"\n{'='*80}\n")
            
            print(f"Error: {e}")
            return f"Sorry, I encountered an error: {str(e)}"