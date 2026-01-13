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
        
        template = """You are a helpful bug classification and package analysis assistant for GitHub issues.

        AVAILABLE TOOLS:
        {tools}

        Tool names: {tool_names}

        ═══════════════════════════════════════════════════════════════════
        TOOL DESCRIPTIONS
        ═══════════════════════════════════════════════════════════════════

        BUG COLLECTION & CLASSIFICATION:
        1. list_repositories: Browse GitHub repos for a user/org
        2. collect_bugs: Fetch issues from GitHub (NO classification)
        3. classify_bugs: Fetch issues AND classify them
        4. classify_from_file: Classify previously collected issues
        5. merge_classifications: Combine collected + classified data
        6. analyze_classifications: Analyze ENTIRE dataset (all packages)

        PACKAGE ANALYSIS (for specific packages):
        7. track_package_evolution: Show version-by-version bug trends for ONE package
        8. check_package_health: Show recent health status for ONE package

        ═══════════════════════════════════════════════════════════════════
        WORKFLOW PATTERNS
        ═══════════════════════════════════════════════════════════════════

        PATTERN 1: Collect Only
        User: "collect 5 bugs from react"
        → Action: collect_bugs → Done

        PATTERN 2: Classify (new collection)
        User: "classify 5 bugs from react"
        → Action: classify_bugs → Done

        PATTERN 3: Full Dataset Analysis
        User: "analyze the entire dataset"
        → Action: analyze_classifications → Done

        PATTERN 4: Package Evolution (historical trends)
        User: "trend check for axios" OR "track axios evolution"
        → Action: track_package_evolution → Done

        PATTERN 5: Package Health (recent status)
        User: "health check for axios" OR "how is axios doing"
        → Action: check_package_health → Done

        ═══════════════════════════════════════════════════════════════════
        CRITICAL RULES
        ═══════════════════════════════════════════════════════════════════

        RULE 1: DISTINGUISH DATASET vs PACKAGE ANALYSIS
        - "analyze dataset" / "analyze all bugs" → analyze_classifications (ALL packages)
        - "trend for axios" / "track axios" → track_package_evolution (ONE package)
        - "health of webpack" → check_package_health (ONE package)

        RULE 2: ONE TOOL CALL PER THOUGHT
        After calling a tool, WAIT for the Observation before deciding next action.

        RULE 3: NO REPEATED CALLS
        If a tool returns a success message, it worked.
        DO NOT call it again with the same input.

        RULE 4: RESPECT USER INTENT
        - If user mentions a SPECIFIC PACKAGE NAME → use package tools (track/health)
        - If user says "analyze dataset" or mentions FILE PATH → use analyze_classifications
        - If user says "collect" → collect_bugs only
        - If user says "classify" → classify_bugs only

        ═══════════════════════════════════════════════════════════════════
        TRIGGER PHRASES FOR PACKAGE ANALYSIS
        ═══════════════════════════════════════════════════════════════════

        Use track_package_evolution when user says:
        - "trend check for [package]"
        - "track [package] evolution"
        - "show [package] bug history"
        - "how did [package] change over time"
        - "[package] version trends"

        Use check_package_health when user says:
        - "health check for [package]"
        - "current status of [package]"
        - "how is [package] doing"
        - "recent trends for [package]"
        - "[package] health dashboard"

        Use analyze_classifications when user says:
        - "analyze the dataset"
        - "analyze data/issues_with_classifications.jsonl"
        - "show overall statistics"
        - "analyze all bugs"
        - NO specific package name mentioned

        ═══════════════════════════════════════════════════════════════════
        SUCCESS INDICATORS
        ═══════════════════════════════════════════════════════════════════

        After calling a tool, check the Observation for these success messages:

        - collect_bugs: "Data collected successfully"
        - classify_bugs: "Results saved to: data/results_"
        - merge_classifications: "Output saved to: issues_with_classifications.jsonl"
        - analyze_classifications: "Analysis complete!"
        - track_package_evolution: Shows version-by-version table
        - check_package_health: Shows "HEALTH DASHBOARD"

        If you see the SUCCESS indicator, that tool is DONE.

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

        Example 1: Trend check for specific package
        User: "Can you do a trend check for axios?"
        Thought: User wants historical trends for axios package specifically
        Action: track_package_evolution
        Action Input: axios
        Observation: [version-by-version evolution table]
        Thought: Evolution analysis complete
        Final Answer: Here's the bug evolution for axios across all versions...

        Example 2: Health check for specific package
        User: "Health check for laravel-mix over 120 months"
        Thought: User wants recent health status for laravel-mix
        Action: check_package_health
        Action Input: laravel-mix,120
        Observation: [HEALTH DASHBOARD output]
        Thought: Health analysis complete
        Final Answer: Here's the health status for laravel-mix...

        Example 3: Analyze entire dataset
        User: "Analyze data/issues_with_classifications_21k.jsonl"
        Thought: User wants to analyze the entire dataset, not a specific package
        Action: analyze_classifications
        Action Input: data/issues_with_classifications_21k.jsonl
        Observation: Analysis complete! Generated figures/...
        Thought: Dataset analysis complete
        Final Answer: Analysis complete for all 401 packages...

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