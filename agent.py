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
            model="qwen2.5:7b-instruct",
            base_url="http://localhost:11434",
            temperature=0.5,
            num_predict=4096
        )
        
        self.tools = create_tools()
        
        template = """You are a bug classification assistant. You help users explore GitHub repositories and classify bugs.

            You have access to these tools:
            {tools}

            Tool names: {tool_names}

            INSTRUCTIONS:
            1. When the user asks to do something, decide which tool to use
            2. You MUST respond EXACTLY in this format (no deviation):

            Thought: [one sentence about what you need to do]
            Action: [exact tool name from the list above]
            Action Input: "[JSON string input for the tool]"

            3. After you see the Observation (tool result), you can either:
            - Use another tool (repeat format above)
            - Give the final answer (format below)

            4. When you have the final answer:

            Thought: I now have the final answer
            Final Answer: [your response to the user]

            CRITICAL RULES:
            - ALWAYS include "Thought:" before your thought
            - ALWAYS include "Action:" before the action  
            - ALWAYS include "Action Input:" before the input
            - Tool names MUST be EXACTLY: {tool_names}
            - IMPORTANT: Action Input MUST be valid JSON.
            For these tools, always pass a JSON string (wrap the whole input in double quotes).

            Examples:
            * For list_repositories: "google"
            * For classify_bugs: "owner/repo,limit" (e.g., "facebook/react,5")
            * For merge_classifications: "collected.jsonl,results.jsonl,output.jsonl"
            * For analyze_classifications: "filename.jsonl"

            EXAMPLES:

            Example 1 - User asks: "show me google repos"
            Thought: [one sentence about what you need to do]
            Action: [exact tool name from the list above]
            Action Input: "[JSON string input for the tool]"

            Example 2 - User asks: "classify 5 bugs from facebook/react"  
            Thought: The user wants to classify 5 bugs from facebook/react
            Action: classify_bugs
            Action Input: "facebook/react,5"

            Example 3 - User asks: "I need 3 bugs from prettier"
            Thought: The user wants 3 bugs from prettier, the repo is prettier/prettier
            Action: classify_bugs
            Action Input: "prettier/prettier,3"

            Now begin!

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
            max_iterations=3
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