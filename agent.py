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
            temperature=0.5,
            num_predict=4096
        )
        
        # Create tools
        self.tools = create_tools()
        
        # Create agent prompt
        template = """You are a helpful bug classification assistant. You help users explore GitHub repositories and classify bug reports.

            You have access to the following tools:

            {tools}

            Tool Names: {tool_names}

            IMPORTANT: You must STRICTLY follow this format. Do NOT deviate:

            Question: the input question you must answer
            Thought: think about what to do (one sentence only)
            Action: MUST be one of [{tool_names}]
            Action Input: the input to the action (simple string, no JSON, no tables)
            Observation: the result of the action
            ... (repeat Thought/Action/Action Input/Observation if needed)
            Thought: I now know the final answer
            Final Answer: the final answer (simple text, NO tables, NO markdown formatting)

            RULES:
            - Use ONLY ONE Action per step
            - Action Input must be a simple string (e.g., "google" or "facebook/react,5")
            - Do NOT create tables or complex formatting
            - Do NOT repeat actions you've already done
            - Keep Final Answer concise and natural

            Previous conversation:
            {chat_history}

            Question: {input}
{agent_scratchpad}"""

        prompt = PromptTemplate.from_template(template)
        
        # Create memory
        self.memory = ConversationBufferMemory(
            memory_key="chat_history",
            return_messages=False
        )
        
        # Create agent
        agent = create_react_agent(
            llm=self.llm,
            tools=self.tools,
            prompt=prompt
        )
        
        # Create agent executor
        self.agent_executor = AgentExecutor(
            agent=agent,
            tools=self.tools,
            memory=self.memory,
            verbose=True,
            handle_parsing_errors=True,
            max_iterations=3
        )
    
    def chat(self, message):
        """Send a message to the agent"""
        import os
        from datetime import datetime
        import io
        import sys
        
        # Create logs directory if needed
        os.makedirs('logs', exist_ok=True)
        
        # Create log file for this session (one per conversation)
        if not hasattr(self, 'session_log'):
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            self.session_log = f"logs/agent_session_{timestamp}.log"
        
        try:
            # Capture stdout (where verbose output goes)
            old_stdout = sys.stdout
            sys.stdout = captured_output = io.StringIO()
            
            # Log the user message to file
            with open(self.session_log, 'a', encoding='utf-8') as f:
                f.write(f"\n{'='*80}\n")
                f.write(f"User: {message}\n")
                f.write(f"Timestamp: {datetime.now().isoformat()}\n")
                f.write(f"{'='*80}\n\n")
            
            # Invoke the agent
            response = self.agent_executor.invoke({"input": message})
            
            # Restore stdout
            sys.stdout = old_stdout
            
            # Get captured output (all the Thought/Action/Observation steps)
            agent_thinking = captured_output.getvalue()
            
            # Print to console
            print(agent_thinking)
            
            # Log everything to file
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