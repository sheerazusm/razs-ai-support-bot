"""
Validator Lambda.

Invoked directly by the orchestrator (not through API Gateway). Takes the
customer's message plus Bedrock's draft reply, and:
  1. Checks the customer message for topics the bot must not handle itself
     (security, refunds, data loss, abuse) and forces escalation.
  2. Adds a standard sign-off so every reply reads consistently.

Keeping this separate from the orchestrator means the "brand safety" rules
can be tested and changed independently of the prompt/Bedrock logic.
"""

from business_context import COMPANY_NAME

ESCALATION_TRIGGERS = [
    "refund",
    "chargeback",
    "hacked",
    "compromised",
    "suspicious login",
    "data loss",
    "lost my files",
    "deleted my files",
    "corrupted",
]

SIGN_OFF = f"\n\n— {COMPANY_NAME} Support"


def handler(event, context):
    message = (event.get("message") or "").lower()
    draft_reply = event.get("draft_reply") or ""

    escalate = any(trigger in message for trigger in ESCALATION_TRIGGERS)

    if escalate:
        reply = (
            "This needs a closer look from a member of our team, so I'm "
            "flagging your message for a human agent to follow up. "
            "They'll be in touch shortly."
        )
    else:
        reply = draft_reply.strip() + SIGN_OFF

    return {"reply": reply, "escalate": escalate}
