from actions import ask_with_memory, ask_without_memory

if __name__ == "__main__":
    while True:
        q = input("\nAsk the agent (or 'quit'): ")
        if q.lower() == "quit":
            break
        print("\nAgent:", ask_with_memory(q))