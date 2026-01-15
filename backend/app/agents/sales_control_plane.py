# backend/app/agents/sales_control_plane.py
"""
Production-Grade Sales AI Control Plane - COMPREHENSIVE VERSION
Implements 13-state conversation flow + 13 sales heuristics + Complete Product Knowledge

This agent sells AI Voice Agents to businesses. It has complete knowledge of:
- Algonox products and capabilities
- Voice AI industry landscape
- ROI calculations and pricing frameworks
- Industry-specific use cases
- Objection handling
- Competitor differentiation
- Customer success stories
"""

from enum import Enum
from typing import Dict, List, Optional, Any, Set, Tuple
from dataclasses import dataclass, field
from datetime import datetime
import re
import hashlib


class ConversationState(Enum):
    """13-state conversation state machine"""
    STATE_0_CALL_START = "CALL_START"
    STATE_1_PERMISSION_MICRO_AGENDA = "PERMISSION_AND_MICRO_AGENDA"
    STATE_2_SAFE_ENTRY_DISCOVERY = "SAFE_ENTRY_DISCOVERY"
    STATE_3_GUARDED_DISCOVERY = "GUARDED_DISCOVERY"
    STATE_4_PROBLEM_NARROWING = "PROBLEM_NARROWING"
    STATE_5_QUANTIFICATION = "QUANTIFICATION_ATTEMPT"
    STATE_6_REFRAME_INSIGHT = "REFRAME_AND_INSIGHT"
    STATE_7_SOLUTION_MAPPING = "SOLUTION_MAPPING"
    STATE_8_OBJECTION_HANDLING = "OBJECTION_HANDLING"
    STATE_9_AUTHORITY_PROCESS = "AUTHORITY_AND_PROCESS_MAPPING"
    STATE_10_RISK_REVERSAL = "RISK_REVERSAL"
    STATE_11_NEXT_STEP = "NEXT_STEP_COMMITMENT"
    STATE_12_EXIT = "EXIT_GRACEFULLY"


class FailureMode(Enum):
    """Failure modes requiring special handling"""
    A_INFO_REFUSAL = "info_refusal"
    B_HOSTILITY = "hostility"
    C_IMMEDIATE_PRICE = "immediate_price"
    D_EARLY_COMPETITOR = "early_competitor"
    E_AUTHORITY_WALL = "authority_wall"
    F_STALLED_CALL = "stalled_call"
    G_LOW_ENERGY = "low_energy"
    H_OVER_TALKING = "over_talking"
    I_SCOPE_CREEP = "scope_creep"
    J_FALSE_COMMITMENT = "false_commitment"


# State transition rules
STATE_TRANSITIONS: Dict[ConversationState, List[ConversationState]] = {
    ConversationState.STATE_0_CALL_START: [
        ConversationState.STATE_1_PERMISSION_MICRO_AGENDA,
        ConversationState.STATE_12_EXIT,
    ],
    ConversationState.STATE_1_PERMISSION_MICRO_AGENDA: [
        ConversationState.STATE_2_SAFE_ENTRY_DISCOVERY,
        ConversationState.STATE_12_EXIT,
    ],
    ConversationState.STATE_2_SAFE_ENTRY_DISCOVERY: [
        ConversationState.STATE_3_GUARDED_DISCOVERY,
        ConversationState.STATE_8_OBJECTION_HANDLING,
        ConversationState.STATE_12_EXIT,
    ],
    ConversationState.STATE_3_GUARDED_DISCOVERY: [
        ConversationState.STATE_4_PROBLEM_NARROWING,
        ConversationState.STATE_8_OBJECTION_HANDLING,
        ConversationState.STATE_12_EXIT,
    ],
    ConversationState.STATE_4_PROBLEM_NARROWING: [
        ConversationState.STATE_5_QUANTIFICATION,
        ConversationState.STATE_6_REFRAME_INSIGHT,
        ConversationState.STATE_8_OBJECTION_HANDLING,
    ],
    ConversationState.STATE_5_QUANTIFICATION: [
        ConversationState.STATE_6_REFRAME_INSIGHT,
        ConversationState.STATE_7_SOLUTION_MAPPING,
        ConversationState.STATE_8_OBJECTION_HANDLING,
    ],
    ConversationState.STATE_6_REFRAME_INSIGHT: [
        ConversationState.STATE_7_SOLUTION_MAPPING,
        ConversationState.STATE_8_OBJECTION_HANDLING,
    ],
    ConversationState.STATE_7_SOLUTION_MAPPING: [
        ConversationState.STATE_8_OBJECTION_HANDLING,
        ConversationState.STATE_9_AUTHORITY_PROCESS,
        ConversationState.STATE_10_RISK_REVERSAL,
    ],
    ConversationState.STATE_8_OBJECTION_HANDLING: [
        ConversationState.STATE_4_PROBLEM_NARROWING,
        ConversationState.STATE_7_SOLUTION_MAPPING,
        ConversationState.STATE_9_AUTHORITY_PROCESS,
        ConversationState.STATE_12_EXIT,
    ],
    ConversationState.STATE_9_AUTHORITY_PROCESS: [
        ConversationState.STATE_10_RISK_REVERSAL,
        ConversationState.STATE_11_NEXT_STEP,
        ConversationState.STATE_8_OBJECTION_HANDLING,
    ],
    ConversationState.STATE_10_RISK_REVERSAL: [
        ConversationState.STATE_11_NEXT_STEP,
        ConversationState.STATE_8_OBJECTION_HANDLING,
    ],
    ConversationState.STATE_11_NEXT_STEP: [
        ConversationState.STATE_12_EXIT,
        ConversationState.STATE_8_OBJECTION_HANDLING,
    ],
    ConversationState.STATE_12_EXIT: [],
}


def generate_elevenlabs_agent_prompt(
    lead_name: str = "",
    lead_company: str = "",
    lead_title: str = "",
    lead_industry: str = "",
    use_cases: List[Dict[str, str]] = None,
    company_analysis: str = "",
) -> str:
    """
    Generate the COMPREHENSIVE ElevenLabs agent prompt with COMPLETE product knowledge.
    This agent knows everything it needs to sell AI voice agents effectively.
    """

    use_cases = use_cases or []
    use_case_text = ""
    for i, uc in enumerate(use_cases[:3], 1):
        use_case_text += f"""
Use Case {i}: {uc.get('title', '')}
- Description: {uc.get('description', '')}
- Impact: {uc.get('impact', '')}
"""

    prompt = f"""You are AADOS, an elite AI Sales Development Representative for Algonox. You are calling to introduce our AI Voice Agent solutions to businesses that can benefit from intelligent automation.

You are NOT a generic chatbot. You are a highly trained sales professional with deep knowledge of AI voice technology, business operations, and consultative selling. Your goal is to have a genuine conversation, understand if there's a fit, and if so, schedule a follow-up meeting.

===========================================
SECTION 1: WHO YOU ARE CALLING
===========================================

**Lead Information:**
- Name: {lead_name or '[Ask for their name]'}
- Company: {lead_company or '[Discover during call]'}
- Title: {lead_title or '[Discover during call]'}
- Industry: {lead_industry or '[Discover during call]'}

**Company Research:**
{company_analysis or 'No prior research available. Discover their situation through conversation.'}

**Pre-Identified Use Cases:**
{use_case_text or 'No specific use cases identified. Discover through conversation.'}

===========================================
SECTION 2: WHAT YOU ARE SELLING
===========================================

**Algonox - Company Overview:**
Algonox is an AI solutions company specializing in intelligent voice agents for enterprise automation. We help businesses automate repetitive phone-based tasks, improve customer experience, and reduce operational costs through conversational AI.

**Core Product: AI Voice Agents**
Our AI voice agents are intelligent, human-like assistants that can:
- Make outbound calls (sales, follow-ups, reminders, surveys)
- Handle inbound calls (customer service, support, inquiries)
- Process complex conversations with natural language understanding
- Integrate with existing business systems (CRM, ERP, databases)
- Work 24/7 without breaks, sick days, or turnover

**Key Capabilities:**
1. **Natural Conversation**: Our agents sound human, not robotic. They understand context, handle interruptions, and respond naturally.
2. **Multi-Language Support**: Support for 29+ languages including English, Spanish, French, German, Hindi, Mandarin, and more.
3. **Real-Time Intelligence**: Agents can access live data, look up customer information, and make decisions during calls.
4. **Seamless Handoff**: When needed, agents can transfer to human agents with full context.
5. **Compliance & Security**: SOC2 compliant, GDPR ready, HIPAA available for healthcare clients.
6. **Custom Training**: Agents are trained on your specific scripts, products, and processes.
7. **Analytics Dashboard**: Real-time monitoring, call recordings, transcripts, and performance metrics.

**Technology Stack:**
- Powered by advanced LLMs (GPT-4, Claude) for reasoning
- ElevenLabs for natural text-to-speech
- Proprietary conversation management system
- Enterprise-grade infrastructure with 99.9% uptime
- API-first architecture for easy integration

===========================================
SECTION 3: WHO BENEFITS FROM THIS
===========================================

**Ideal Customer Profile:**
- Companies making/receiving 500+ calls per month
- Teams spending 20+ hours weekly on phone tasks
- Businesses with repetitive call workflows
- Companies struggling with hiring/retention for phone roles
- Organizations needing 24/7 phone coverage
- Businesses expanding internationally (language support)

**Industries We Serve Best:**

1. **Healthcare & Medical:**
   - Appointment scheduling and reminders (reduce no-shows by 40-60%)
   - Patient follow-up calls
   - Insurance verification
   - Prescription refill reminders
   - Post-visit surveys
   - Lab result notifications
   - ROI: Typically save 15-25 hours/week per practice

2. **Financial Services & Insurance:**
   - Lead qualification and follow-up
   - Policy renewal reminders
   - Claims status updates
   - Payment reminders
   - Account verification
   - Cross-sell/upsell campaigns
   - ROI: 3-5x increase in contact rates, 40% cost reduction

3. **Real Estate:**
   - Lead qualification
   - Property inquiry follow-up
   - Showing scheduling
   - Post-showing feedback
   - Rent collection reminders
   - Maintenance request handling
   - ROI: Agents follow up with 100% of leads within minutes

4. **E-commerce & Retail:**
   - Order status inquiries
   - Return/exchange processing
   - Abandoned cart recovery (recover 15-25% of carts)
   - Customer satisfaction surveys
   - Product recommendations
   - Loyalty program outreach
   - ROI: 24/7 support without staffing costs

5. **Logistics & Transportation:**
   - Delivery notifications
   - Schedule changes
   - Driver dispatch
   - Customer ETA updates
   - Proof of delivery confirmation
   - Exception handling
   - ROI: Reduce customer service calls by 50%

6. **Professional Services (Legal, Accounting):**
   - Appointment scheduling
   - Document request follow-up
   - Payment reminders
   - Client intake calls
   - Case status updates
   - ROI: Free up 10-20 billable hours per week

7. **Home Services (HVAC, Plumbing, Electrical):**
   - Appointment booking
   - Service reminders
   - Quote follow-up
   - Customer satisfaction calls
   - Review request campaigns
   - ROI: Book 30% more appointments from leads

8. **Hospitality & Restaurants:**
   - Reservation management
   - Confirmation calls
   - Waitlist management
   - Special event promotion
   - Feedback collection
   - ROI: Reduce phone staff needs by 60-80%

9. **Education & Training:**
   - Enrollment inquiries
   - Class reminders
   - Attendance follow-up
   - Parent communication
   - Alumni outreach
   - ROI: Handle 5x more inquiries during peak enrollment

10. **B2B Sales Organizations:**
    - Lead qualification
    - Meeting scheduling
    - Follow-up sequences
    - Re-engagement campaigns
    - Event registration
    - ROI: 3x pipeline coverage, 50% more meetings booked

===========================================
SECTION 4: ROI & VALUE CALCULATIONS
===========================================

**Cost of Manual Calling:**
- Average phone rep salary: $35,000-55,000/year
- With benefits, training, management: $50,000-75,000/year
- Plus: Turnover costs (avg 30-40% annual turnover in call centers)
- Plus: Hiring time (2-4 weeks to find, 2-4 weeks to train)
- Plus: Inconsistency (bad days, sick days, vacations)

**AI Voice Agent Economics:**
- Handles unlimited calls simultaneously
- Works 24/7/365
- No turnover, no training time for new hires
- Consistent performance every call
- Scales instantly for campaigns

**ROI Calculator Framework:**
When quantifying value, use this formula collaboratively:
1. "How many [calls/tasks] does your team handle weekly?"
2. "How long does each typically take?"
3. "What would you estimate that costs in labor? Maybe $X/hour?"
4. "So that's roughly [hours × rate] = $X per week, or $Y per year."
5. "If we could handle 70-80% of those automatically, that's potential savings of..."

**Typical Results by Use Case:**
- Outbound Sales Calls: 3-5x more conversations, 40-60% cost savings
- Appointment Reminders: 40-60% reduction in no-shows
- Customer Service: 50-70% call deflection, 24/7 availability
- Lead Qualification: 100% follow-up within minutes, 2-3x conversion
- Collections/Reminders: 25-40% improvement in collection rates
- Surveys: 5-10x more responses than email

===========================================
SECTION 5: PRICING FRAMEWORK
===========================================

**IMPORTANT: Never quote specific prices. Use these frameworks:**

When asked about pricing, say:
"Pricing depends on a few factors - call volume, complexity, and integrations needed. Most businesses in your size range invest somewhere between $2,000-10,000 per month, but the real question is the ROI. Let me understand your situation better so I can tell you if this even makes sense for you."

**Pricing Factors:**
- Call volume (usage-based component)
- Number of use cases/agents
- Integration complexity
- Custom development needs
- Support level required

**Value Anchoring:**
"If we can save you 20 hours per week at even $30/hour, that's $2,400/month in labor alone. Most clients see full ROI within the first 2-3 months."

**Pilot Programs:**
"We typically start with a focused pilot - one use case, 2-4 weeks, limited scope. This lets you prove the value before any bigger commitment. Pilot pricing is usually a few thousand dollars depending on complexity."

===========================================
SECTION 6: COMPETITIVE LANDSCAPE
===========================================

**Never disparage competitors. Position on fit and strengths.**

**Key Competitors & How to Position:**

1. **Traditional Call Centers/BPOs:**
   Position: "They're great for complex situations. Where we shine is the repetitive, high-volume stuff where consistency and 24/7 availability matter most."

2. **IVR/Phone Trees:**
   Position: "IVR systems are useful but limited. Our agents have actual conversations - they understand context, handle follow-ups, and feel human."

3. **Chatbots/Text-Based AI:**
   Position: "Chat is great for certain things, but many customers still prefer or need phone calls. We complement chat by handling voice interactions."

4. **Other AI Voice Vendors:**
   - If they mention a specific competitor, say: "They're solid. The question is really fit for your specific needs. What's working and what's missing in your evaluation?"
   - Our differentiators: Enterprise-grade reliability, custom training depth, integration flexibility, white-glove implementation support.

5. **DIY/Internal Development:**
   Position: "Building in-house is an option. The question is timeline and resources. Most teams find it takes 6-12 months and significant engineering effort. We get you live in 2-4 weeks."

===========================================
SECTION 7: OBJECTION HANDLING PLAYBOOK
===========================================

**When they object, use the LAER-C Framework:**

**L - LISTEN:** Let them finish completely. Don't interrupt. Take a breath before responding.

**A - ACKNOWLEDGE:** Show empathy without agreeing or disagreeing.
- "I appreciate you sharing that..."
- "That's a fair concern, and you're not alone in raising it..."
- "I hear you..."

**E - EXPLORE:** Dig deeper with open questions to understand the real concern.
- "Help me understand - is it more about [A] or [B]?"
- "What would need to be true for this to work for you?"
- "Is that the main concern, or is there something else behind it?"

**R - RESPOND:** Address the specific concern with tailored proof and examples.
- Use success stories from Section 8
- Provide specific data and results

**C - CONFIRM:** Test that the objection is resolved before moving on.
- "Does that address your concern?"
- "Is there more to it, or are we good on that point?"
- "What else would you need to feel comfortable?"

**Common Objections and Responses:**

**"We don't have budget for this"**
Response: "That makes sense - most teams we work with aren't coming in with allocated budget. That's actually why we do focused pilots - small investment to prove the value. Quick question though: what's the cost right now of NOT solving this? If your team is spending 20 hours a week on calls at $40/hour, that's over $40,000 a year. Our pilot would be a fraction of one month's cost to potentially eliminate that forever."

**"We're not interested"**
Response: "Totally fair, and I appreciate you being direct. Before I let you go - is it that automation isn't on your radar at all, or is it more about timing? I ask because about half the people who say 'not interested' initially actually mean 'not right now' or 'not the way you positioned it.'"

**"We're happy with our current process/vendor"**
Response: "That's great to hear - if it's working, don't fix it. Out of curiosity, what's working well? And if you could wave a magic wand, what's the ONE thing you'd improve about how you handle [calls/customer service]?"

**"We tried AI before and it didn't work"**
Response: "I hear that a lot actually. Can I ask what you tried and what went wrong? The technology has changed dramatically in the last 12-18 months. Most of the early solutions were basically glorified IVR systems. What we're doing is fundamentally different - these are actual conversational agents. But I'd love to understand your past experience so I can be straight with you about whether we'd have the same issues."

**"Send me some information"**
Response: "Happy to. Quick question before I do - when you look at that info, what specifically will you be evaluating? I want to make sure I send you the right stuff, not just generic marketing materials. What would actually be useful?"

**"I need to talk to my boss/team"**
Response: "Makes sense - these decisions rarely happen solo. Who else would weigh in on this? And what would they need to see or hear to feel comfortable? Maybe it makes sense to include them in our next conversation so we're all on the same page."

**"We don't have time to implement something new"**
Response: "Totally get it - bandwidth is tight everywhere. Here's the thing though: our implementation is 2-4 weeks, and most of the work is on our side. Your team's involvement is maybe 3-4 hours total. The question is: can you afford NOT to free up [X] hours per week for your team? What would they do with that time?"

**"How do I know this will work for us?"**
Response: "Great question. That's exactly why we do pilots. We start with one focused use case, run it for 2-4 weeks, and measure everything. If it doesn't hit the metrics we agreed on, you walk away. No long-term commitment until you've seen proof."

**"What about quality/accuracy?"**
Response: "Our agents are typically 95%+ accurate in understanding and responding. But more importantly, every call is recorded and transcribed. You can review them, we track quality metrics, and the agent improves over time based on real conversations. Plus, for anything complex, we set up instant handoff to your team."

**"What about security/compliance?"**
Response: "Critical question. We're SOC2 Type II certified, GDPR compliant, and we have HIPAA-compliant deployments for healthcare. All data is encrypted, we don't store sensitive information longer than needed, and we can work within your security requirements. Happy to have our team do a security review with yours."

**"AI is going to replace jobs"**
Response: "I understand that concern. Here's how we see it: AI handles the repetitive stuff so your people can focus on complex, high-value work. Most of our clients redeploy team members to work that actually requires human judgment - they don't lay people off. The AI handles the calls that were burning people out anyway."

**"We're too small/big for this"**
Response: "Actually, we work with companies ranging from 10-person teams to enterprises with thousands of employees. The key question isn't size - it's volume and repetitiveness. If you're making 500+ calls a month on repetitive tasks, there's usually a strong case. What does your call volume look like?"

===========================================
SECTION 8: SUCCESS STORIES
===========================================

**Use these stories to provide proof. Anonymize if needed.**

**Healthcare - Regional Medical Group:**
"We worked with a medical group with 12 locations. They were missing about 25% of appointments - typical for the industry. Their staff was spending 4 hours daily just calling reminders. We deployed a reminder agent, and within 6 weeks, no-shows dropped to under 10%. That freed up their front desk staff to actually help patients in the office instead of being on the phone all day."

**Financial Services - Insurance Agency:**
"An insurance agency was struggling with lead follow-up. Their agents were maybe getting to 30% of leads within 24 hours - the rest went cold. Our AI agent now calls every lead within 5 minutes, qualifies them, and books appointments for the human agents. They're booking 3x more appointments with the same team."

**Real Estate - Property Management:**
"A property management company with 2,000 units was drowning in maintenance calls. Residents would call, wait on hold, get frustrated. We deployed a 24/7 intake agent that logs requests directly into their system. They now handle 80% of calls automatically, and residents actually prefer it because there's no hold time."

**E-commerce - Online Retailer:**
"An e-commerce company was losing about 70% of abandoned carts. They tried email sequences but got maybe 3% recovery. We deployed an AI agent that calls within an hour of cart abandonment, has a natural conversation, and offers to help complete the order. They're now recovering 18% of carts - that's hundreds of thousands in revenue they were leaving on the table."

**Professional Services - Law Firm:**
"A law firm was missing potential clients because they couldn't answer phones during court hours. We deployed an intake agent that qualifies potential clients, collects case details, and schedules consultations. They increased new client consultations by 40% without adding staff."

===========================================
SECTION 9: CONVERSATION FLOW
===========================================

Follow this 13-state progression. ALWAYS know which state you're in.

**STATE 0 - CALL_START:**
- Introduce yourself clearly: "Hi [Name], this is AADOS calling from Algonox."
- Sound warm and human, not scripted
- Immediately move to STATE 1

**STATE 1 - PERMISSION_AND_MICRO_AGENDA:**
- Ask permission: "Did I catch you at a bad time?"
- Set micro-agenda: "I'll be brief - noticed [trigger] and wanted to share a quick thought about how companies like yours are using AI for [relevant task]."
- Offer easy exit: "If it doesn't resonate, totally fine to say so."
- If bad time: "No problem! When would be better to reconnect - later today or tomorrow morning?" Then end call.
- If permission granted: Move to STATE 2

**STATE 2 - SAFE_ENTRY_DISCOVERY (SPIN: Situation):**
- Share credible trigger: "I noticed [specific observation about their company/role/industry]"
- Ask SITUATION questions to understand their current state:
  - "How are you currently handling [phone tasks/customer calls]?"
  - "Walk me through a typical workflow for [relevant process]"
  - "What tools or systems do you use for this today?"
- Listen for interest, then move to STATE 3
- **TRIAL CLOSE:** "Based on what you've shared, this sounds worth exploring further. Fair?"

**STATE 3 - GUARDED_DISCOVERY (SPIN: Problem):**
- Use RANGES, not open-ended: "When companies in [industry] handle [task], they typically spend 10-20 hours weekly or 40+ hours. Where do you land?"
- Ask PROBLEM questions to uncover pain points:
  - "What's the biggest challenge with your current approach?"
  - "Where do things tend to break down?"
  - "What frustrates your team most about this process?"
- Mirror-Label-Summarize: Repeat key words, label emotions, confirm understanding
- Gather 2-3 data points, then narrow in STATE 4

**STATE 4 - PROBLEM_NARROWING (SPIN: Problem + Implication):**
- Pick ONE problem: "Of everything we discussed, [specific issue] seems like the biggest pain point. Is that fair?"
- Ask IMPLICATION questions to amplify the pain:
  - "What happens when this problem isn't addressed?"
  - "How does this impact your team's ability to [achieve goal]?"
  - "What's the cost of NOT solving this - in time, money, or customer satisfaction?"
  - "How does this affect employee morale or turnover?"
- Confirm it's worth solving, move to STATE 5
- **TRIAL CLOSE:** "If the math works out, would this be worth a deeper look?"

**STATE 5 - QUANTIFICATION_ATTEMPT (SPIN: Implication):**
- Quantify together: "If your team spends [X] hours weekly on that at roughly $[Y]/hour, that's about $[Z] per week. Does that math feel roughly right?"
- Build the business case collaboratively:
  - "What else does this problem cost you that's harder to measure?"
  - "How many opportunities do you think slip through the cracks?"
- Don't interrogate - collaborate

**STATE 6 - REFRAME_AND_INSIGHT (SPIN: Need-Payoff + Challenger):**
- **CHALLENGER INSIGHT - TEACH something surprising:**
  - "Here's what most teams miss: the real cost isn't just the hours. It's the 60% of leads that go cold because no one followed up within 5 minutes."
  - "We analyzed 10,000 calls and found consistency beats talent. Your best rep on their worst day is worse than AI on any day."
  - "The hidden cost is usually [turnover, missed opportunities, customer churn, compliance risk]."
- **TAILOR to their situation:**
  - "For [their industry], the biggest impact is usually [specific insight]"
  - "Given your [size/role], the main benefit would be [specific area]"
- **TAKE CONTROL:**
  - "Let me suggest a different way to look at this..."
  - "What if we focused on [high-impact area] first?"
- Ask NEED-PAYOFF questions:
  - "If we eliminated [problem], what would that free your team to do?"
  - "What would it mean for your business if [calls/tasks] were handled automatically?"
  - "How would your day change without this headache?"
- Create aha moment
- **TRIAL CLOSE:** "Does this approach make sense for your situation?"

**STATE 7 - SOLUTION_MAPPING:**
- Connect to solution: "This is actually a perfect use case for what we do. Our AI agents handle exactly this type of [call/task]."
- Use relevant success story: "A [similar company] we work with [specific result]."
- Keep high-level - no demos on first call

**STATE 8 - OBJECTION_HANDLING (Use LAER-C Framework):**
- **L - LISTEN:** Let them finish completely. Take a breath.
- **A - ACKNOWLEDGE:** "I appreciate you sharing that..." or "That's a fair concern..."
- **E - EXPLORE:** "Is that the main concern, or is there something else?" / "Help me understand - is it [A] or [B]?"
- **R - RESPOND:** Use specific objection responses from Section 7 with proof and examples
- **C - CONFIRM:** "Does that address your concern, or is there more to it?"
- Only proceed to STATE 9 after objection is CONFIRMED resolved

**STATE 9 - AUTHORITY_AND_PROCESS_MAPPING:**
- Map stakeholders: "Besides yourself, who else would weigh in?"
- Understand process: "What's typically the evaluation process for something like this?"
- Plan inclusion: "Should we loop them in for our next conversation?"

**STATE 10 - RISK_REVERSAL:**
- Remove risk: "Here's what I'd suggest - a focused pilot. One use case, 2-4 weeks, we measure everything. If it doesn't hit the numbers we agree on, you walk away. No long-term commitment until you've seen proof."
- Address concerns preemptively

**STATE 11 - NEXT_STEP_COMMITMENT (Assumptive Close):**
- **TRIAL CLOSE first:** "It sounds like we're aligned on the problem. Should we talk about next steps?"
- Use ASSUMPTIVE language (assume they're moving forward):
  - "When we get started, here's how the process works..."
  - "For our next conversation, I'll bring [specific value]..."
- Be SPECIFIC: "How about this - I'll send a 2-page summary today. You review it, and we reconnect Thursday at 2pm to discuss next steps. Does that work?"
- Confirm details: time, attendees, what you'll send
- Get verbal commitment
- If hesitation: "What would need to be true for you to feel good about moving forward?"

**STATE 12 - EXIT_GRACEFULLY:**
- Thank them genuinely
- Recap specifically: "Great, so I'll send [X] by [time], and we'll talk [day] at [time]."
- Warm close: "Thanks for your time, [Name]. Looking forward to our conversation on [day]. Take care!"
- END THE CALL IMMEDIATELY AFTER YOUR CLOSING - do not wait or ask additional questions

===========================================
SECTION 10: CRITICAL RULES
===========================================

**NEVER DO THESE:**
- Quote specific prices (use ranges and frameworks)
- Guarantee results (use "typically" and "in our experience")
- Disparage competitors (position on fit instead)
- Use pushy language ("buy now", "limited time", "act fast")
- Ask for sensitive data on first call
- Ask the same question twice
- Talk more than 30% of the time
- Continue after your closing statement

**ALWAYS DO THESE:**
- Ask for permission before proceeding
- Listen more than you talk
- Use their name occasionally (not excessively)
- Acknowledge their concerns genuinely
- Provide specific examples and stories
- Quantify value in their terms
- End calls cleanly and promptly

===========================================
SECTION 11: CALL ENDING - CRITICAL
===========================================

**YOU MUST END THE CALL PROACTIVELY. DO NOT WAIT FOR THE PROSPECT.**

**End the call immediately after:**
1. Delivering your closing statement (thanks + recap)
2. Confirming a scheduled meeting
3. The prospect says goodbye/thanks/take care
4. The prospect asks to be removed or not interested
5. Any STATE 12 completion

**How to end:**
After your final statement, STOP SPEAKING. The call will end automatically.
Do NOT say "Is there anything else?" after closing.
Do NOT wait for them to hang up.

**Example Endings:**
- SUCCESS: "Perfect, I'll send that summary today and we'll connect Thursday at 2. Thanks [Name], talk soon!" [STOP - CALL ENDS]
- CALLBACK: "No problem, I'll try you [day/time]. Have a great day!" [STOP - CALL ENDS]
- NOT INTERESTED: "Understood, I appreciate your time. Have a great day!" [STOP - CALL ENDS]
- HOSTILE: "I apologize for the interruption. I'll remove you from our list. Goodbye." [STOP - CALL ENDS]

**CRITICAL: Once you deliver your closing, the conversation is OVER. Immediately stop speaking.**

===========================================
BEGIN THE CALL
===========================================

You are now ready. Start in STATE 0 - introduce yourself warmly and move to asking permission. Remember: be human, be curious, be helpful. You're exploring whether there's genuine fit, not forcing a sale.

If there's a fit, schedule a follow-up. If not, exit gracefully. Both outcomes are success.

BEGIN NOW."""

    return prompt


def generate_voice_settings() -> Dict[str, Any]:
    """
    Generate optimal ElevenLabs voice settings for clear, professional sales calls.
    """
    return {
        "stability": 0.75,
        "similarity_boost": 0.80,
        "style": 0.35,
        "use_speaker_boost": True,
        "optimize_streaming_latency": 3,
    }


def generate_conversation_config() -> Dict[str, Any]:
    """
    Generate ElevenLabs conversation configuration with proper call ending.
    """
    return {
        "conversation": {
            "max_duration_seconds": 600,
            "initial_state": "CALL_START",
            "end_call_on": [
                "goodbye",
                "bye",
                "bye bye",
                "take care",
                "talk soon",
                "talk to you soon",
                "looking forward to it",
                "have a good day",
                "have a great day",
                "thank you for your time",
                "thanks for your time",
                "i appreciate your time",
                "i'll remove you from our list",
                "thanks, talk soon",
                "great talking with you",
                "thanks for chatting",
            ],
        },
        "tts": {
            "voice_id": None,
            "model_id": "eleven_turbo_v2_5",
            "voice_settings": generate_voice_settings(),
            "output_format": "pcm_16000",
        },
        "stt": {
            "model_id": "nova-2",
            "language": "en",
        },
        "llm": {
            "model_id": "gpt-4o",
            "temperature": 0.7,
            "max_tokens": 300,
        },
        "turn_detection": {
            "type": "end_of_speech",
            "threshold": 0.5,
            "prefix_padding_ms": 300,
            "silence_duration_ms": 700,
        },
        "tools": [
            {
                "type": "end_call",
                "name": "end_call",
                "description": "End the phone call immediately. Use this right after delivering your closing statement. Do not wait for the prospect to respond.",
            }
        ],
    }


# =============================================================================
# CONVERSATION TRACKER - Prevents Repetition & Tracks Context
# =============================================================================

@dataclass
class QuestionRecord:
    """Track a question that was asked"""
    question_text: str
    question_hash: str
    question_type: str
    state_when_asked: str
    timestamp: datetime
    got_answer: bool = False
    answer_summary: str = ""


@dataclass
class TopicRecord:
    """Track topics that have been discussed"""
    topic: str
    first_mentioned_by: str
    depth_explored: int
    key_insights: List[str] = field(default_factory=list)


class ConversationTracker:
    """
    Real-time conversation tracking to prevent repetitive questions
    and enable adaptive responses.
    """

    # Memory limits for transcript storage
    MAX_QUESTIONS_STORED = 100
    MAX_TOPICS_STORED = 50

    def __init__(self, conversation_id: str = ""):
        self.conversation_id = conversation_id
        self.created_at = datetime.utcnow()  # For garbage collection
        self.current_state = ConversationState.STATE_0_CALL_START
        self.state_history: List[Tuple[ConversationState, datetime]] = []

        self.asked_questions: List[QuestionRecord] = []
        self.question_hashes: Set[str] = set()
        self.topics_discussed: Dict[str, TopicRecord] = {}

        self.gathered_info: Dict[str, Any] = {
            "pain_points": [],
            "current_solutions": [],
            "budget_signals": [],
            "timeline_signals": [],
            "authority_info": [],
            "objections": [],
            "interests": [],
            "company_context": {},
        }

        self.detected_failure_modes: List[Tuple[FailureMode, datetime, str]] = []
        self.failure_mode_responses: Dict[str, int] = {}

        self.turn_count = 0
        self.agent_talk_ratio = 0.0
        self.prospect_engagement_score = 5
        self.energy_level = "medium"

        self.used_phrases: Set[str] = set()
        self.used_transitions: Set[str] = set()
        self.used_questions_by_type: Dict[str, List[str]] = {}

        # SPIN question tracking (Gong research: 11-14 questions optimal)
        self.spin_counts: Dict[str, int] = {
            "situation": 0,
            "problem": 0,
            "implication": 0,
            "need_payoff": 0
        }
        self.OPTIMAL_QUESTION_MIN = 11
        self.OPTIMAL_QUESTION_MAX = 14

        # Trial close tracking
        self.trial_closes_made: int = 0
        self.trial_closes_positive: int = 0
        self.TARGET_TRIAL_CLOSES = 4  # 3-5 per call

        # Challenger insight tracking
        self.challenger_insights_delivered: int = 0

    def _hash_question(self, question: str) -> str:
        normalized = question.lower()
        fillers = ['um', 'uh', 'like', 'you know', 'basically', 'actually', 'so', 'well']
        for filler in fillers:
            normalized = normalized.replace(filler, '')
        normalized = ' '.join(normalized.split())
        return hashlib.md5(normalized.encode()).hexdigest()[:12]

    def _extract_question_type(self, question: str) -> str:
        question_lower = question.lower()
        if any(w in question_lower for w in ['how much', 'cost', 'price', 'budget', 'spend', 'invest']):
            return "budget"
        elif any(w in question_lower for w in ['who else', 'decision', 'stakeholder', 'team', 'boss', 'manager']):
            return "authority"
        elif any(w in question_lower for w in ['when', 'timeline', 'deadline', 'urgency', 'timing']):
            return "timeline"
        elif any(w in question_lower for w in ['challenge', 'problem', 'pain', 'struggle', 'difficult', 'frustrat']):
            return "pain_discovery"
        elif any(w in question_lower for w in ['currently', 'today', 'right now', 'using', 'handle', 'process']):
            return "current_state"
        elif any(w in question_lower for w in ['make sense', 'interested', 'open to', 'worth', 'helpful']):
            return "commitment"
        elif any(w in question_lower for w in ['tell me more', 'elaborate', 'explain', 'what do you mean']):
            return "clarification"
        else:
            return "general"

    def _classify_spin_type(self, question: str) -> Optional[str]:
        """Classify question into SPIN category."""
        q_lower = question.lower()

        # SITUATION questions - understand current state
        if any(w in q_lower for w in [
            'how are you currently', 'walk me through', 'what tools', 'what systems',
            'how do you handle', 'tell me about your', 'what does your process',
            'how many', 'how often', 'who handles'
        ]):
            return "situation"

        # PROBLEM questions - uncover pain points
        if any(w in q_lower for w in [
            'biggest challenge', 'frustrat', 'difficult', 'struggle', 'problem',
            'pain', 'break down', 'not working', 'issues with', 'concerns about'
        ]):
            return "problem"

        # IMPLICATION questions - amplify consequences
        if any(w in q_lower for w in [
            'what happens when', 'impact', 'cost of not', 'affect',
            'consequence', 'if this continues', 'how does this impact',
            'what does it cost you', 'miss out', 'slip through'
        ]):
            return "implication"

        # NEED-PAYOFF questions - paint solution picture
        if any(w in q_lower for w in [
            'if we could', 'what would it mean', 'how would your day change',
            'what would that free', 'imagine if', 'what would success look like',
            'if this was solved', 'benefit', 'value'
        ]):
            return "need_payoff"

        return None

    def record_spin_question(self, question: str) -> None:
        """Track a question by its SPIN category."""
        spin_type = self._classify_spin_type(question)
        if spin_type and spin_type in self.spin_counts:
            self.spin_counts[spin_type] += 1

    def record_trial_close(self, was_positive: bool = False) -> None:
        """Track a trial close attempt."""
        self.trial_closes_made += 1
        if was_positive:
            self.trial_closes_positive += 1

    def record_challenger_insight(self) -> None:
        """Track delivery of a Challenger insight."""
        self.challenger_insights_delivered += 1

    def get_spin_balance(self) -> Dict[str, int]:
        """Get current SPIN question counts."""
        return self.spin_counts.copy()

    def is_ready_for_pitch(self) -> Tuple[bool, str]:
        """Check if enough discovery has been done before pitching."""
        total_questions = len(self.asked_questions)
        if total_questions < self.OPTIMAL_QUESTION_MIN:
            return (False, f"Need {self.OPTIMAL_QUESTION_MIN - total_questions} more discovery questions before pitching")
        if total_questions > self.OPTIMAL_QUESTION_MAX:
            return (True, "Transition to solution - optimal question count reached")
        return (True, "Question count optimal for solution mapping")

    def get_methodology_score(self) -> Dict[str, Any]:
        """Calculate overall methodology compliance score."""
        total_questions = len(self.asked_questions)
        total_spin = sum(self.spin_counts.values())

        spin_compliance = (total_spin / max(total_questions, 1)) * 100 if total_questions > 0 else 0
        trial_close_compliance = (self.trial_closes_made / self.TARGET_TRIAL_CLOSES) * 100
        question_count_optimal = self.OPTIMAL_QUESTION_MIN <= total_questions <= self.OPTIMAL_QUESTION_MAX

        return {
            "total_questions": total_questions,
            "spin_questions": total_spin,
            "spin_compliance_pct": round(spin_compliance, 1),
            "spin_breakdown": self.spin_counts.copy(),
            "trial_closes": self.trial_closes_made,
            "trial_close_compliance_pct": min(round(trial_close_compliance, 1), 100),
            "challenger_insights": self.challenger_insights_delivered,
            "question_count_optimal": question_count_optimal,
            "engagement_score": self.prospect_engagement_score,
        }

    def is_question_already_asked(self, question: str, similarity_threshold: float = 0.5) -> Tuple[bool, Optional[QuestionRecord]]:
        q_hash = self._hash_question(question)

        if q_hash in self.question_hashes:
            for record in self.asked_questions:
                if record.question_hash == q_hash:
                    return (True, record)

        q_lower = question.lower()
        q_type = self._extract_question_type(question)

        stop_words = {'what', 'your', 'with', 'that', 'this', 'have', 'from', 'they', 'been', 'will', 'would', 'could', 'about', 'there', 'their', 'which', 'when', 'where', 'does', 'like'}
        q_words = set(w for w in q_lower.split() if len(w) > 3 and w not in stop_words)

        for record in self.asked_questions:
            record_lower = record.question_text.lower()
            record_words = set(w for w in record_lower.split() if len(w) > 3 and w not in stop_words)

            if q_words and record_words:
                intersection = len(q_words & record_words)
                union = len(q_words | record_words)
                similarity = intersection / union if union > 0 else 0

                if record.question_type == q_type and similarity > similarity_threshold:
                    return (True, record)
                if similarity > 0.6:
                    return (True, record)

                key_concepts = {'biggest', 'challenge', 'problem', 'process', 'current', 'spend', 'time', 'budget', 'decision', 'team'}
                q_concepts = q_words & key_concepts
                record_concepts = record_words & key_concepts

                if q_concepts and q_concepts == record_concepts and similarity > 0.3:
                    return (True, record)

        return (False, None)

    def record_question(self, question: str, got_answer: bool = False, answer_summary: str = "") -> None:
        q_hash = self._hash_question(question)
        q_type = self._extract_question_type(question)

        record = QuestionRecord(
            question_text=question,
            question_hash=q_hash,
            question_type=q_type,
            state_when_asked=self.current_state.value,
            timestamp=datetime.utcnow(),
            got_answer=got_answer,
            answer_summary=answer_summary,
        )

        self.asked_questions.append(record)
        self.question_hashes.add(q_hash)

        # Enforce memory limit - keep only recent questions
        if len(self.asked_questions) > self.MAX_QUESTIONS_STORED:
            # Remove oldest questions
            removed = self.asked_questions[:-self.MAX_QUESTIONS_STORED]
            self.asked_questions = self.asked_questions[-self.MAX_QUESTIONS_STORED:]
            # Update hash set to match remaining questions
            self.question_hashes = {q.question_hash for q in self.asked_questions}

        if q_type not in self.used_questions_by_type:
            self.used_questions_by_type[q_type] = []
        self.used_questions_by_type[q_type].append(question)

    def record_topic(self, topic: str, mentioned_by: str = "prospect", insight: str = "") -> None:
        topic_key = topic.lower().strip()

        if topic_key in self.topics_discussed:
            self.topics_discussed[topic_key].depth_explored += 1
            if insight:
                self.topics_discussed[topic_key].key_insights.append(insight)
        else:
            self.topics_discussed[topic_key] = TopicRecord(
                topic=topic,
                first_mentioned_by=mentioned_by,
                depth_explored=1,
                key_insights=[insight] if insight else [],
            )

    def record_gathered_info(self, category: str, info: str) -> None:
        if category in self.gathered_info:
            if isinstance(self.gathered_info[category], list):
                if info not in self.gathered_info[category]:
                    self.gathered_info[category].append(info)

    def detect_failure_mode(self, prospect_response: str) -> Optional[FailureMode]:
        """
        Detect all 10 failure modes from prospect responses.
        Returns the most relevant failure mode or None.
        """
        response_lower = prospect_response.lower()
        word_count = len(prospect_response.split())

        # A. INFO REFUSAL - Prospect won't share information
        if any(phrase in response_lower for phrase in [
            "can't share", "confidential", "not comfortable", "don't want to say",
            "that's private", "can't tell you", "not at liberty"
        ]):
            return FailureMode.A_INFO_REFUSAL

        # B. HOSTILITY - Prospect is hostile or wants to end call
        if any(phrase in response_lower for phrase in [
            "stop calling", "not interested", "leave me alone", "don't call again",
            "don't call me", "waste of time", "scam", "spam", "don't contact",
            "take me off", "remove me"
        ]):
            return FailureMode.B_HOSTILITY

        # C. IMMEDIATE PRICE - Asking for price too early
        if any(phrase in response_lower for phrase in [
            "how much", "what's the price", "cost", "pricing", "what do you charge"
        ]) and self.current_state.value in ["CALL_START", "PERMISSION_AND_MICRO_AGENDA", "SAFE_ENTRY_DISCOVERY"]:
            return FailureMode.C_IMMEDIATE_PRICE

        # D. EARLY COMPETITOR - Mentions competitor early in the call
        competitor_phrases = [
            "we use", "already have", "currently using", "working with",
            "other vendor", "existing solution", "already implemented", "signed with"
        ]
        if any(phrase in response_lower for phrase in competitor_phrases) and self.turn_count < 5:
            return FailureMode.D_EARLY_COMPETITOR

        # E. AUTHORITY WALL - Not the decision maker
        if any(phrase in response_lower for phrase in [
            "not my decision", "need to ask my boss", "i don't handle that",
            "talk to someone else", "not the right person", "above my pay grade"
        ]):
            return FailureMode.E_AUTHORITY_WALL

        # F. STALLED CALL - Non-committal responses, conversation going nowhere
        if any(phrase in response_lower for phrase in [
            "i don't know", "not sure", "maybe", "i guess"
        ]) and self.turn_count > 6:
            return FailureMode.F_STALLED_CALL

        # G. LOW ENERGY - Short, disengaged responses
        if word_count < 5 and self.turn_count > 4:
            consecutive_short = sum(1 for q in self.asked_questions[-3:]
                                  if q.got_answer and len(q.answer_summary.split()) < 5)
            if consecutive_short >= 2:
                return FailureMode.G_LOW_ENERGY

        # H. OVER TALKING - Prospect signals agent is talking too much
        over_talking_phrases = [
            "let me stop you", "hold on", "wait a second", "slow down",
            "too much information", "i need to go", "running out of time",
            "can we speed this up", "get to the point", "cut to the chase"
        ]
        if any(phrase in response_lower for phrase in over_talking_phrases):
            return FailureMode.H_OVER_TALKING

        # I. SCOPE CREEP - Prospect keeps expanding requirements
        scope_creep_phrases = [
            "we also need", "another thing", "what about", "can it also",
            "does it include", "we'd also want", "on top of that",
            "additionally", "plus we need"
        ]
        if any(phrase in response_lower for phrase in scope_creep_phrases) and self.turn_count > 8:
            return FailureMode.I_SCOPE_CREEP

        # J. FALSE COMMITMENT - Empty promises, no real intent
        false_commitment_phrases = [
            "send me something", "send me an email", "i'll look at it later",
            "call me back", "maybe next quarter", "we'll see",
            "let me think about it", "i'll get back to you"
        ]
        # Check for pattern: false commitments with low engagement
        if any(phrase in response_lower for phrase in false_commitment_phrases):
            if self.turn_count > 10 and self.prospect_engagement_score < 4:
                return FailureMode.J_FALSE_COMMITMENT

        return None

    def get_failure_mode_response(self, mode: FailureMode) -> str:
        """Get a response template for handling a detected failure mode."""
        responses = {
            FailureMode.A_INFO_REFUSAL: [
                "Totally fair, I appreciate you being upfront. Let me share what we've seen work for similar companies instead...",
                "No problem at all. Instead of specifics, can I share a general pattern we've noticed with companies like yours?",
                "Completely understand. Let me take a different approach - I'll share some anonymous examples that might resonate.",
            ],
            FailureMode.B_HOSTILITY: [
                "I apologize if I caught you at a bad time. Would another day work better?",
                "I hear you, and I respect that. Is there a better time, or should I take you off our list?",
                "Got it. I appreciate you being direct. Have a great day.",
            ],
            FailureMode.C_IMMEDIATE_PRICE: [
                "Great question - pricing really depends on scope. Quick question first: what's the main challenge you're hoping to address?",
                "Happy to discuss pricing - it varies based on what you need. What's driving your interest today?",
                "I can definitely get to that. To give you an accurate range, help me understand: what problem are you trying to solve?",
            ],
            FailureMode.D_EARLY_COMPETITOR: [
                "That's great that you have something in place. Quick question - if you could change one thing about your current setup, what would it be?",
                "Interesting! How's that been working for you? What made you look at that originally?",
                "Good to know. A lot of our clients started with similar solutions. What's working well, and what's been frustrating?",
            ],
            FailureMode.E_AUTHORITY_WALL: [
                "Makes total sense. Who would be the right person to loop in? I'd love to include them in the conversation.",
                "Understood. Could you point me to the right person? Or would it help if I sent you something to share with them?",
                "Got it. What would make it easier for you to bring this to their attention?",
            ],
            FailureMode.F_STALLED_CALL: [
                "You know what, let me ask a different question. If you could wave a magic wand and fix one process, what would it be?",
                "Let me take a step back. What made you pick up the phone today - just curious, or is something actually bugging you?",
                "I'm sensing we might be going in circles. What would actually be useful for you to know right now?",
            ],
            FailureMode.G_LOW_ENERGY: [
                "Let me share a quick story that might be relevant...",
                "I'll cut to the chase - here's the one thing that usually surprises teams like yours...",
                "You know what's interesting? A company about your size told me they had the exact same reaction at first...",
            ],
            FailureMode.H_OVER_TALKING: [
                "I hear you - let me pause. What's the one thing you want to know?",
                "Good point, I should listen more. What questions do you have for me?",
                "Fair enough - what would be most useful for me to focus on?",
            ],
            FailureMode.I_SCOPE_CREEP: [
                "Those are all great points. Let me suggest we focus on one key area first, then we can expand from there.",
                "I want to make sure we nail the core need before adding complexity. What's the #1 priority?",
                "All good requirements. Let's start with the biggest pain point - which of those keeps you up at night?",
            ],
            FailureMode.J_FALSE_COMMITMENT: [
                "I appreciate that. Before we wrap up - is there something specific that would make this a clear yes or no for you?",
                "Sure, I can do that. Just to level-set - what would need to be true for this to become a priority?",
                "Happy to send info. Quick question - on a scale of 1-10, how likely is this to get attention? I want to be respectful of your time.",
            ],
        }

        mode_responses = responses.get(mode, ["Let me try a different approach..."])
        mode_key = mode.value
        used_count = self.failure_mode_responses.get(mode_key, 0)
        response = mode_responses[used_count % len(mode_responses)]
        self.failure_mode_responses[mode_key] = used_count + 1
        return response

    def transition_state(self, new_state: ConversationState) -> bool:
        allowed = STATE_TRANSITIONS.get(self.current_state, [])
        if new_state in allowed:
            self.state_history.append((self.current_state, datetime.utcnow()))
            self.current_state = new_state
            return True
        return False

    def get_context_summary(self) -> str:
        summary_parts = []
        summary_parts.append(f"CURRENT STATE: {self.current_state.value}")

        if self.asked_questions:
            recent_questions = [q.question_text for q in self.asked_questions[-5:]]
            summary_parts.append(f"QUESTIONS ALREADY ASKED (DO NOT REPEAT):\n- " + "\n- ".join(recent_questions))

        if self.topics_discussed:
            topics = [f"{t.topic} (depth: {t.depth_explored})" for t in self.topics_discussed.values()]
            summary_parts.append(f"TOPICS COVERED: {', '.join(topics)}")

        info_items = []
        for category, items in self.gathered_info.items():
            if items and isinstance(items, list) and len(items) > 0:
                info_items.append(f"- {category}: {', '.join(str(i) for i in items[:3])}")
        if info_items:
            summary_parts.append(f"INFORMATION GATHERED:\n" + "\n".join(info_items))

        if self.detected_failure_modes:
            recent_modes = [m[0].value for m in self.detected_failure_modes[-2:]]
            summary_parts.append(f"DETECTED CHALLENGES: {', '.join(recent_modes)}")

        summary_parts.append(f"ENGAGEMENT: {self.prospect_engagement_score}/10, Energy: {self.energy_level}")
        return "\n\n".join(summary_parts)

    def get_suggested_next_action(self) -> str:
        suggestions = {
            ConversationState.STATE_0_CALL_START: "Introduce yourself and immediately ask for permission.",
            ConversationState.STATE_1_PERMISSION_MICRO_AGENDA: "Share credible trigger and ask ONE safe question.",
            ConversationState.STATE_2_SAFE_ENTRY_DISCOVERY: "Use range-based questions to explore their situation.",
            ConversationState.STATE_3_GUARDED_DISCOVERY: "Mirror their words, then narrow to ONE specific workflow.",
            ConversationState.STATE_4_PROBLEM_NARROWING: "Confirm the problem, then quantify collaboratively.",
            ConversationState.STATE_5_QUANTIFICATION: "Calculate ROI together: time × cost = impact.",
            ConversationState.STATE_6_REFRAME_INSIGHT: "Share an insight they don't have.",
            ConversationState.STATE_7_SOLUTION_MAPPING: "Connect their problem to our solution with a success story.",
            ConversationState.STATE_8_OBJECTION_HANDLING: "Isolate-Clarify-Test the objection.",
            ConversationState.STATE_9_AUTHORITY_PROCESS: "Map stakeholders and decision process.",
            ConversationState.STATE_10_RISK_REVERSAL: "Offer a low-risk pilot.",
            ConversationState.STATE_11_NEXT_STEP: "Close with SPECIFIC mutual action plan.",
            ConversationState.STATE_12_EXIT: "Thank them, recap next steps, END THE CALL.",
        }
        return suggestions.get(self.current_state, "Continue naturally.")


# =============================================================================
# QUESTION VARIATIONS FOR DISCOVERY
# =============================================================================

QUESTION_VARIATIONS = {
    "pain_discovery": [
        "When teams like yours tackle {topic}, they usually spend 10-20 hours weekly or 40+ hours. Where do you land?",
        "On a scale of 1-10, how much of a headache is {topic} for your team right now?",
        "If you had to pick the ONE thing that slows your team down most, what would it be?",
        "What's the thing that keeps coming up in team meetings that nobody wants to deal with?",
        "If I asked your team what frustrates them most day-to-day, what would they say?",
    ],
    "current_state": [
        "How are you handling {topic} today? Manual process, spreadsheets, or something else?",
        "Walk me through a typical {topic} workflow - what does that look like?",
        "What tools or processes do you have in place for {topic}?",
        "When {topic} comes up, who usually handles it and how?",
    ],
    "budget": [
        "When you've invested in solutions like this before, what range were you typically looking at?",
        "Is there a budget already allocated, or would we need to make a case for it?",
        "How does your team typically evaluate ROI for investments like this?",
    ],
    "authority": [
        "Besides yourself, who else would weigh in on something like this?",
        "What's typically the process when you evaluate new tools?",
        "If this made sense, what would the next steps look like on your end?",
        "Who else would need to be comfortable with this before moving forward?",
    ],
    "timeline": [
        "Is there a particular deadline or event driving the timing?",
        "If you were going to solve this, when would you want it in place?",
        "What's the urgency level - 'nice to have' or 'need to fix now'?",
    ],
    "commitment": [
        "Based on what we've discussed, does it make sense to continue this conversation?",
        "Is this something you'd want to explore further?",
        "Would it be helpful if I sent a quick summary and we reconnected later this week?",
    ],
}

TRANSITION_PHRASES = [
    "That makes sense.",
    "I hear you.",
    "Got it.",
    "Interesting.",
    "That's helpful to know.",
    "Thanks for sharing that.",
    "I appreciate the context.",
    "That's a good point.",
]


def get_varied_question(question_type: str, topic: str = "", tracker: Optional[ConversationTracker] = None) -> str:
    variations = QUESTION_VARIATIONS.get(question_type, [])
    if not variations:
        return ""

    if tracker:
        used_count = len(tracker.used_questions_by_type.get(question_type, []))
        idx = used_count % len(variations)
        question = variations[idx]
        if question_type not in tracker.used_questions_by_type:
            tracker.used_questions_by_type[question_type] = []
        tracker.used_questions_by_type[question_type].append(question)
    else:
        question = variations[0]

    return question.format(topic=topic) if "{topic}" in question else question


def get_varied_transition(tracker: Optional[ConversationTracker] = None) -> str:
    if tracker:
        available = [p for p in TRANSITION_PHRASES if p not in tracker.used_transitions]
        if not available:
            tracker.used_transitions.clear()
            available = TRANSITION_PHRASES
        phrase = available[0]
        tracker.used_transitions.add(phrase)
        return phrase
    return TRANSITION_PHRASES[0]


# =============================================================================
# ENHANCED PROMPT WITH CONTEXT INJECTION
# =============================================================================

def generate_enhanced_prompt(
    lead_name: str = "",
    lead_company: str = "",
    lead_title: str = "",
    lead_industry: str = "",
    use_cases: List[Dict[str, str]] = None,
    company_analysis: str = "",
    conversation_context: str = "",
) -> str:
    base_prompt = generate_elevenlabs_agent_prompt(
        lead_name=lead_name,
        lead_company=lead_company,
        lead_title=lead_title,
        lead_industry=lead_industry,
        use_cases=use_cases,
        company_analysis=company_analysis,
    )

    if conversation_context:
        context_section = f"""
===========================================
REAL-TIME CONVERSATION CONTEXT
===========================================
{conversation_context}

Use this context to:
1. NEVER repeat questions already asked
2. Build on information gathered
3. Handle detected challenges appropriately
4. Stay in the correct conversation state
"""
        base_prompt = base_prompt.replace(
            "BEGIN NOW.",
            context_section + "\nCONTINUE FROM CURRENT STATE."
        )

    return base_prompt


# =============================================================================
# GLOBAL TRACKER STORAGE - Thread-Safe with Memory Management
# =============================================================================

import asyncio
import threading
from datetime import timedelta

# Global tracker storage with thread safety
_conversation_trackers: Dict[str, ConversationTracker] = {}
_tracker_lock = threading.Lock()  # Use threading.Lock for sync access
_async_tracker_lock: Optional[asyncio.Lock] = None  # Lazy init for async access

# Memory limits
MAX_TRACKERS = 1000  # Maximum number of trackers to keep
TRACKER_MAX_AGE_HOURS = 2  # Auto-cleanup after 2 hours


def _get_async_lock() -> asyncio.Lock:
    """Get or create the async lock (lazy initialization)."""
    global _async_tracker_lock
    if _async_tracker_lock is None:
        _async_tracker_lock = asyncio.Lock()
    return _async_tracker_lock


def get_or_create_tracker(conversation_id: str) -> ConversationTracker:
    """
    Thread-safe tracker retrieval/creation (synchronous version).

    Use this in synchronous contexts. For async contexts, use
    get_or_create_tracker_async() instead.
    """
    with _tracker_lock:
        if conversation_id not in _conversation_trackers:
            # Enforce memory limit
            if len(_conversation_trackers) >= MAX_TRACKERS:
                _cleanup_stale_trackers_sync()

            _conversation_trackers[conversation_id] = ConversationTracker(conversation_id)
        return _conversation_trackers[conversation_id]


async def get_or_create_tracker_async(conversation_id: str) -> ConversationTracker:
    """
    Thread-safe tracker retrieval/creation (async version).

    Use this in async contexts for proper non-blocking behavior.
    """
    async with _get_async_lock():
        if conversation_id not in _conversation_trackers:
            # Enforce memory limit
            if len(_conversation_trackers) >= MAX_TRACKERS:
                await _cleanup_stale_trackers_async()

            _conversation_trackers[conversation_id] = ConversationTracker(conversation_id)
        return _conversation_trackers[conversation_id]


def clear_tracker(conversation_id: str) -> None:
    """Thread-safe tracker removal (synchronous version)."""
    with _tracker_lock:
        _conversation_trackers.pop(conversation_id, None)


async def clear_tracker_async(conversation_id: str) -> None:
    """Thread-safe tracker removal (async version)."""
    async with _get_async_lock():
        _conversation_trackers.pop(conversation_id, None)


def get_tracker_count() -> int:
    """Get current number of active trackers (for monitoring)."""
    with _tracker_lock:
        return len(_conversation_trackers)


def _cleanup_stale_trackers_sync() -> int:
    """
    Remove stale trackers (synchronous, called within lock).
    Returns number of trackers removed.
    """
    now = datetime.utcnow()
    max_age = timedelta(hours=TRACKER_MAX_AGE_HOURS)

    stale_ids = [
        cid for cid, tracker in _conversation_trackers.items()
        if (now - tracker.created_at) > max_age
    ]

    for cid in stale_ids:
        del _conversation_trackers[cid]

    return len(stale_ids)


async def _cleanup_stale_trackers_async() -> int:
    """
    Remove stale trackers (async version, called within async lock).
    Returns number of trackers removed.
    """
    now = datetime.utcnow()
    max_age = timedelta(hours=TRACKER_MAX_AGE_HOURS)

    stale_ids = [
        cid for cid, tracker in _conversation_trackers.items()
        if (now - tracker.created_at) > max_age
    ]

    for cid in stale_ids:
        del _conversation_trackers[cid]

    return len(stale_ids)


async def cleanup_all_trackers() -> int:
    """
    Force cleanup of all trackers. Call on shutdown.
    Returns number of trackers cleared.
    """
    async with _get_async_lock():
        count = len(_conversation_trackers)
        _conversation_trackers.clear()
        return count
