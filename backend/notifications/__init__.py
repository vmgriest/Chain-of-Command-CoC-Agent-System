"""Human escalation channels for the CEO tier.  (M4)

email.py      — SMTP to human_admin.email
push.py       — Web Push to human_admin.push_topic
scheduling.py — surface human_admin.scheduling_link to the customer

⚠ Notifying a human NEVER ends the chat session. See backend/graph/tiers/ceo.py.
"""
