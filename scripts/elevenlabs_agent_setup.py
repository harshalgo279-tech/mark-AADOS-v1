#!/usr/bin/env python3
"""
ElevenLabs Sales Agent Setup Automation Script

This script automates the setup of an ElevenLabs Conversational AI agent
for the AADOS (AI Agents Driven Outbound Sales) system.

Prerequisites:
1. pip install playwright
2. playwright install chromium
3. ElevenLabs account with API access

Usage:
    python elevenlabs_agent_setup.py

The script will:
1. Open ElevenLabs in a browser (you'll need to sign in manually)
2. Create a new agent with Algonox sales configuration
3. Configure the system prompt, voice, and tools
4. Set up post-call webhook
5. Output the Agent ID and configuration details
"""

import asyncio
import os
import sys
import time
from datetime import datetime

# Agent configuration for Algonox sales
AGENT_CONFIG = {
    "name": "Algonox Sales Agent",
    "first_message": """Hi, this is Alex calling from Algonox. I'm reaching out because we've been helping companies in your industry transform their operations with AI automation. Do you have a moment to chat?""",
    "system_prompt": """# Personality

You are Alex, a friendly, professional, and results-driven sales representative for Algonox. You are warm, confident, and genuinely interested in understanding customer needs. You speak in a conversational, natural tone—never robotic or pushy.

# Environment

You are handling outbound sales calls for Algonox, a leading AI solutions provider specializing in enterprise automation and intelligent agents. We help businesses transform operations through AI technology, delivering measurable ROI through process automation, intelligent assistants, and data-driven insights.

# Tone

- Keep responses concise (2-3 sentences unless more detail is needed)
- Be warm and professional with brief affirmations ("Absolutely," "Great question," "I understand")
- Adapt your communication style based on the customer's tone
- Use conversational language—avoid jargon unless the customer uses it
- Never be pushy; focus on understanding needs first

# Goal

Qualify leads and guide them toward a demo booking through this workflow:

1. Greet warmly and establish rapport
2. Identify the customer's needs with open-ended questions
3. Present relevant solutions based on their specific situation
4. Handle objections with empathy and clear value propositions
5. Collect contact information if not already known
6. Book a demo or schedule a follow-up
7. Summarize next steps clearly

This step is important: Always understand customer needs before presenting solutions.

# Algonox Services

Our core services include:
1. AI-Powered Process Automation: Streamline repetitive workflows and reduce operational costs
2. Intelligent Virtual Agents: Deploy conversational AI for customer service, sales, and internal support
3. Knowledge Management Solutions: Extract insights from documents, calls, and data sources
4. Custom AI Development: Tailored solutions for unique business challenges

# Key Questions to Ask

- "What challenges are you currently facing with manual processes or repetitive tasks?"
- "What's prompting you to look for AI solutions right now?"
- "What would success look like for your team if you could automate some of these workflows?"
- "What's your timeline for implementing something like this?"
- "Who else is involved in evaluating new technology solutions?"

# Handling Objections

## Price Concerns
Acknowledge the concern, then focus on value and ROI. Ask about their current costs from manual processes.

## Timing
Understand their timeline. If not urgent, schedule a follow-up and offer to send relevant case studies.

## Need to Think About It
Ask what specific concerns they have. Offer to send additional information and schedule a brief follow-up.

## Already Have Solutions
Ask what's working well and what could be improved. Highlight how Algonox complements existing tools.

# Guardrails

- Never make promises about features that don't exist
- Never pressure customers; respect when they're not ready
- If unsure about product details, offer to follow up with accurate information
- Never speak negatively about competitors
- Always confirm next steps before ending the call
- Collect customer email before the call ends

This step is important: Collect customer contact information before the call ends.

# Character Normalization

When collecting email addresses:
- Spoken: "john dot smith at company dot com"
- Written: "john.smith@company.com"
- Convert "at" to "@", "dot" to ".", remove spaces

When collecting phone numbers:
- Spoken: "five five five, one two three, four five six seven"
- Written: "555-123-4567"

# Error Handling

If any tool call fails:
1. Acknowledge: "I'm having a bit of trouble pulling that up right now."
2. Don't guess or make up information
3. Offer alternatives: "Let me get your contact info and have someone follow up with those details."

# Dynamic Variables Available

The following lead information is available:
- {{lead_name}}: The lead's full name
- {{lead_title}}: Their job title
- {{lead_company}}: Their company name
- {{lead_industry}}: Their industry
- {{lead_email}}: Their email (if known)
- {{lead_phone}}: Their phone number

Use these to personalize the conversation.""",

    "voice_id": "kdmDKE6EkgrWrrykO9Qt",  # Alexandra - young, professional female
    "model": "gpt-4o",

    # Success evaluation criteria
    "evaluation_criteria": [
        {
            "name": "lead_qualified",
            "prompt": "Mark as successful if the agent identified the customer's needs, pain points, and timeline. The customer should have provided meaningful information about their requirements."
        },
        {
            "name": "contact_collected",
            "prompt": "Mark as successful if the agent collected the customer's email address or phone number during the conversation."
        },
        {
            "name": "meeting_booked",
            "prompt": "Mark as successful if a demo, call, or meeting was scheduled with the customer."
        },
        {
            "name": "positive_interaction",
            "prompt": "Mark as successful if the customer remained engaged and the conversation ended on a positive note, regardless of whether they purchased or booked a meeting."
        },
    ],

    # Data collection fields
    "data_collection": [
        {"identifier": "customer_name", "type": "string", "description": "Extract the customer's full name from the conversation."},
        {"identifier": "customer_email", "type": "string", "description": "Extract the customer's email address in written format (e.g., john@company.com)."},
        {"identifier": "customer_phone", "type": "string", "description": "Extract the customer's phone number if provided."},
        {"identifier": "company_name", "type": "string", "description": "Extract the name of the customer's company or organization."},
        {"identifier": "primary_need", "type": "string", "description": "Summarize the customer's main need or pain point in one sentence."},
        {"identifier": "decision_timeline", "type": "string", "description": "Extract when the customer plans to make a decision."},
        {"identifier": "next_steps", "type": "string", "description": "Summarize the agreed-upon next steps from the conversation."},
        {"identifier": "objections_raised", "type": "string", "description": "List any objections or concerns the customer raised during the call."},
        {"identifier": "demo_requested", "type": "boolean", "description": "Did the customer agree to or request a demo?"},
    ],
}


async def setup_agent_manual_guide():
    """
    Print manual setup guide since automated setup requires authentication.
    """
    print("\n" + "="*80)
    print("ELEVENLABS SALES AGENT - MANUAL SETUP GUIDE")
    print("="*80)

    print("""
STEP 1: Sign In to ElevenLabs
-----------------------------
1. Go to https://elevenlabs.io/app/agents
2. Sign in with your ElevenLabs account
3. If you don't have an account, create one at https://elevenlabs.io/app/sign-up

STEP 2: Create New Agent
------------------------
1. Click "Create Agent" or "+ New Agent"
2. Enter agent name: "Algonox Sales Agent"
3. Select "Blank template"
4. Click "Create"

STEP 3: Configure First Message
-------------------------------
In the "Agent" tab, set the First Message to:
""")
    print("-"*40)
    print(AGENT_CONFIG["first_message"])
    print("-"*40)

    print("""
STEP 4: Configure System Prompt
-------------------------------
Copy and paste the following system prompt:
""")
    print("-"*40)
    print(AGENT_CONFIG["system_prompt"])
    print("-"*40)

    print("""
STEP 5: Select LLM Model
------------------------
Go to Model Settings and select:
- Recommended: GPT-4o or Claude Sonnet
- These provide the best balance of speed and intelligence for sales

STEP 6: Configure Voice
-----------------------
Go to the "Voice" tab:
1. Select voice: Alexandra (ID: kdmDKE6EkgrWrrykO9Qt)
   - Or choose another professional voice from the library
2. Voice Settings:
   - Stability: 0.55 (slightly expressive for engaging delivery)
   - Similarity: 0.80
   - Speed: 1.0x

STEP 7: Add Knowledge Base Documents
------------------------------------
Go to "Knowledge Base" and add:
- Product/service information
- Pricing details
- FAQ documents
- Case studies
- Company background

STEP 8: Configure Success Evaluation
------------------------------------
Go to "Analysis" tab and add these criteria:

1. Lead Qualified:
   "Mark as successful if the agent identified the customer's needs,
   pain points, and timeline."

2. Contact Collected:
   "Mark as successful if the agent collected the customer's email
   address or phone number."

3. Meeting Booked:
   "Mark as successful if a demo, call, or meeting was scheduled."

4. Positive Interaction:
   "Mark as successful if the conversation ended on a positive note."

STEP 9: Configure Data Collection
---------------------------------
Add these data collection fields:
- customer_name (string): Customer's full name
- customer_email (string): Customer's email address
- customer_phone (string): Customer's phone number
- company_name (string): Customer's company
- primary_need (string): Main need/pain point
- decision_timeline (string): When they plan to decide
- next_steps (string): Agreed next steps
- demo_requested (boolean): Did they request a demo?

STEP 10: Set Up Post-Call Webhook
---------------------------------
1. Go to Settings > Webhooks
2. Add webhook URL: [YOUR_SERVER_URL]/api/calls/elevenlabs/post-call
3. Save the webhook secret securely
4. Add the secret to your .env file as ELEVENLABS_WEBHOOK_SECRET

STEP 11: Copy Agent ID
----------------------
1. After saving, find your Agent ID in the agent settings
2. Add it to your .env file as ELEVENLABS_AGENT_ID

STEP 12: Test the Agent
-----------------------
1. Click "Test AI Agent" button
2. Have a test conversation
3. Verify the agent follows the configured behavior
4. Check that data collection works correctly

""")

    print("="*80)
    print("ENVIRONMENT VARIABLES TO SET")
    print("="*80)
    print("""
Add these to your backend/.env file:

ELEVENLABS_API_KEY=your_api_key_here
ELEVENLABS_AGENT_ID=your_agent_id_here
ELEVENLABS_WEBHOOK_SECRET=your_webhook_secret_here
ELEVENLABS_VOICE_ID=kdmDKE6EkgrWrrykO9Qt
ELEVENLABS_POST_CALL_WEBHOOK_URL=https://your-server.com/api/calls/elevenlabs/post-call
""")


async def setup_with_playwright():
    """
    Attempt to set up the agent using Playwright automation.
    Falls back to manual guide if authentication is needed.
    """
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        print("Playwright not installed. Install with: pip install playwright")
        print("Then run: playwright install chromium")
        await setup_agent_manual_guide()
        return

    print("Starting ElevenLabs Agent Setup...")
    print("A browser window will open. Please sign in to your ElevenLabs account.")

    async with async_playwright() as p:
        # Launch browser in headed mode so user can sign in
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context()
        page = await context.new_page()

        # Navigate to ElevenLabs agents page
        await page.goto("https://elevenlabs.io/app/agents")

        print("\n" + "="*60)
        print("PLEASE SIGN IN TO YOUR ELEVENLABS ACCOUNT")
        print("="*60)
        print("\nAfter signing in, press Enter to continue with setup...")

        # Wait for user to sign in
        input()

        # Check if we're on the agents page
        current_url = page.url
        if "sign-in" in current_url.lower():
            print("Still on sign-in page. Please complete sign-in and press Enter...")
            input()

        # Wait for agents page to load
        await page.wait_for_timeout(2000)

        print("\nAttempting to create new agent...")

        try:
            # Look for "Create Agent" or "+ New Agent" button
            create_button = await page.query_selector('button:has-text("Create Agent"), button:has-text("New Agent"), button:has-text("+ New")')

            if create_button:
                await create_button.click()
                await page.wait_for_timeout(1000)

                print("Agent creation dialog opened.")
                print("\nPlease complete the following manually:")
                print(f"1. Agent Name: {AGENT_CONFIG['name']}")
                print("2. Select 'Blank template'")
                print("3. Click Create")
                print("\nPress Enter after creating the agent...")
                input()

                # Wait for agent editor to load
                await page.wait_for_timeout(2000)

                print("\nAgent created! Now copy the configuration from the guide below.")

            else:
                print("Could not find Create Agent button. Please create the agent manually.")

        except Exception as e:
            print(f"Automation error: {e}")
            print("Please continue setup manually.")

        # Print the manual configuration guide
        await setup_agent_manual_guide()

        print("\n" + "="*60)
        print("Browser will remain open for you to complete the setup.")
        print("Close the browser when done.")
        print("="*60)

        # Keep browser open for manual completion
        print("\nPress Enter to close the browser...")
        input()

        await browser.close()


def save_config_to_file():
    """Save agent configuration to a JSON file for reference."""
    import json

    config_file = os.path.join(os.path.dirname(__file__), "elevenlabs_agent_config.json")

    with open(config_file, "w", encoding="utf-8") as f:
        json.dump(AGENT_CONFIG, f, indent=2, ensure_ascii=False)

    print(f"\nAgent configuration saved to: {config_file}")


def main():
    """Main entry point."""
    print("\n" + "="*80)
    print("AADOS - ELEVENLABS SALES AGENT SETUP")
    print("="*80)

    print("""
This script will help you set up an ElevenLabs Conversational AI agent
for the AADOS outbound sales system.

Options:
1. Interactive setup with Playwright (browser automation)
2. Print manual setup guide only
3. Save configuration to file

Enter your choice (1/2/3): """, end="")

    choice = input().strip()

    if choice == "1":
        asyncio.run(setup_with_playwright())
    elif choice == "2":
        asyncio.run(setup_agent_manual_guide())
    elif choice == "3":
        save_config_to_file()
        asyncio.run(setup_agent_manual_guide())
    else:
        print("Invalid choice. Printing manual guide...")
        asyncio.run(setup_agent_manual_guide())

    print("\n" + "="*80)
    print("Setup complete! Remember to update your .env file with the agent credentials.")
    print("="*80)


if __name__ == "__main__":
    main()
