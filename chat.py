from agent import BugAgent

def main():
    print("\n" + "="*60)
    print("In-Ex Bug Classification Agent")
    print("="*60)
    print("\nType 'exit' to quit\n")
    
    # Create agent
    agent = BugAgent()
    
    while True:
        # Get user input
        user_input = input("You: ").strip()
        
        # Check for exit
        if user_input.lower() in ['exit', 'quit']:
            print("\nGoodbye!\n")
            break
        
        # Skip empty
        if not user_input:
            continue
        
        # Get response from agent
        try:
            response = agent.chat(user_input)
            print(f"\nAgent: {response}\n")
        except Exception as e:
            print(f"\nError: {e}\n")

if __name__ == '__main__':
    main()