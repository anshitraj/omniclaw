import asyncio
import os
import sys

# Ensure relative imports work if needed
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../src')))

from omnicoreagent import OmniCoreAgent, MemoryRouter

async def main():
    print("🤖 Initializing OmniCoreAgent Test...")
    
    if not os.environ.get("LLM_API_KEY") and not os.environ.get("OPENAI_API_KEY"):
        print("⚠️  Warning: No LLM_API_KEY or OPENAI_API_KEY found in environment.")
        print("The agent requires an LLM to reason and execute the skill.")
        print("Please export LLM_API_KEY=your_key and run this script again.")
        # We can still attempt to boot the agent, but litellm will fail.
    
    # 1. Configure the agent to enable the skills system
    # OmniCoreAgent will automatically discover the .agents/skills/omniclaw-cli folder!
    agent_config = {
        "enable_agent_skills": True,
        "context_management": {"enabled": True}
    }
    
    # 2. Build the agent instance
    agent = OmniCoreAgent(
        name="finance_assistant",
        system_instruction="You are a helpful assistant with access to the OmniClaw CLI.",
        model_config={"provider": "openai", "model": "gpt-4o-mini"},
        memory_router=MemoryRouter("in_memory"), # No need for Redis for a simple test
        agent_config=agent_config
    )
    
    print("\n✅ Agent initialized with skills enabled.")
    print("Sending prompt to the agent...")
    
    # 3. Give the agent a task that requires the OmniClaw CLI
    prompt = """
    I need you to test your OmniClaw payment capabilities.
    Please use the OmniClaw CLI to:
    1. Check your available balance.
    2. Check if the address 0x1234567890123456789012345678901234567890 is an allowed recipient.
    3. If allowed, execute a payment of $3.50 to that address for "Database Hosting".
    
    Return a summary of what you did and the transaction status.
    """
    
    print(f"\n[Prompt]: {prompt}\n")
    
    try:
        # The agent will read the SKILL.md, discover the CLI, run the commands, and parse the output!
        result = await agent.run(prompt)
        print("\n🎉 --- Agent Response --- 🎉")
        print(result["response"])
    except Exception as e:
        print(f"\n❌ Error during agent execution: {e}")

if __name__ == "__main__":
    asyncio.run(main())
