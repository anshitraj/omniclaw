import asyncio
import os
import sys

# Ensure relative imports work if needed
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../src')))

from dotenv import load_dotenv

# Load project environment variables
load_dotenv()

from omnicoreagent import OmniCoreAgent, MemoryRouter, ToolRegistry

async def main():
    print("🤖 Initializing OmniCoreAgent SDK Test...")
    
    agent_config = {
        "enable_agent_skills": True,
        "context_management": {"enabled": True},
        "guardrail_mode": "off",
        "max_steps": 30,
        "tool_call_timeout": 300
    }
    
    agent = OmniCoreAgent(
        name="omniclaw_tester",
        system_instruction="""You are a powerful AI agent. 
        You have access to the bash shell. 
        Your primary directive right now is to test the OmniClaw CLI. 
        You must read the OmniClaw SKILL file (if you haven't automatically), install the CLI locally as instructed in the SKILL, configure it, and then run a balance check.""",
        model_config={"provider": "openai", "model": "gpt-4o-mini"}, # Local fallback/mocking might occur if no key
        memory_router=MemoryRouter("in_memory"),
        agent_config=agent_config,
        debug=True
    )
    
    prompt = """
    Please perform the full OmniClaw local installation and test loop!
    1. Read your skills to find the local installation command for OmniClaw.
    2. Write and execute a bash script (using your tools) that installs the CLI locally via pip.
    3. Run the configuration command.
    4. Check the balance and return it to me.
    """
    
    print(f"\n[Prompt]: {prompt}\n")
    
    try:
        result = await agent.run(prompt)
        print("\n🎉 --- Agent Response --- 🎉")
        print(result["response"])
    except Exception as e:
        print(f"\n❌ Expected Error (if no API keys are present): {e}")
        print("The script successfully loaded the agent and attempted to execute the prompt.")

if __name__ == "__main__":
    asyncio.run(main())
