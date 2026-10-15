"""
Runs the Pydantic AI team on one ticket and turns the result into audit events.

The Boss reads the ticket, delegates across the team, and returns a structured
resolution. Any payment it proposes is re-read from the database through MCP
before it is offered to a human, so a hallucinated figure can never reach the
cash path.
"""

from __future__ import annotations

from datetime import datetime

from pydantic_ai.usage import UsageLimits

from backend.agents import AgentUnavailable, TicketResolution, build_team

# Keeps one ticket inside the shop's token budget even if an agent gets chatty.
RUN_LIMITS = UsageLimits(request_limit=30)
from backend.mcp_client import ToolRecorder

TYPE_BRIEF = {
    "customer_order": (
        "A customer has ordered something. Find out whether we can actually fill it, "
        "what is blocking it if not, and what the customer should be told."),
    "rent_notice": (
        "The landlord has sent a rent notice. Confirm the terms and the deadline, and "
        "work out whether we can pay it."),
    "price_override": (
        "Someone is asking for a discount. Confirm we can fill the order, then work out "
        "what price still protects our margin before anyone quotes a number."),
}


def _brief(ticket) -> str:
    bits = [
        f"Ticket {ticket['id']} ({ticket['type']}) from {ticket['requester']}.",
        f"Subject: {ticket['subject']}.",
    ]
    if ticket["sku"]:
        bits.append(f"Item: {ticket['sku']} size {ticket['size']}, quantity {ticket['qty']}.")
    if ticket["invoice_id"]:
        bits.append(f"Linked invoice id: {ticket['invoice_id']}.")
    if ticket["lease_id"]:
        bits.append(f"Linked lease id: {ticket['lease_id']}.")
    if ticket["notes"]:
        bits.append(f"Notes on the ticket: {ticket['notes']}")
    bits.append(TYPE_BRIEF.get(ticket["type"], "Work this ticket."))
    bits.append(
        "Delegate to the right specialists with ask_teammate, read every figure from the "
        "tools, and come back with what was decided. If money must leave the account, say "
        "so and give the exact amount you read from the database — a human will release it.")
    return " ".join(bits)


def run_agent_team(ticket, today: str, money, days_until):
    """
    Returns (events, pending_approval).

    Raises AgentUnavailable if the model cannot be reached, so the caller can
    decide what to do about it.
    """
    tid = ticket["id"]
    rec = ToolRecorder()
    events = []

    def emit(agent, action, output, status="complete", tools=None, **extra):
        events.append({
            "timestamp": datetime.now().isoformat(),
            "agent": agent,
            "action": action,
            "ticket_id": tid,
            "tools_used": list(tools) if tools is not None else rec.take(),
            "output": output,
            "status": status,
            "engine": "pydantic-ai",
            **extra,
        })

    def on_delegate(caller, callee, question, answer, tools_used):
        events.append({
            "timestamp": datetime.now().isoformat(),
            "agent": callee,
            "action": f"Answer {caller}",
            "ticket_id": tid,
            "tools_used": list(tools_used),
            "output": answer,
            "status": "complete",
            "engine": "pydantic-ai",
            "delegated_by": caller,
            "question": question,
        })

    try:
        team = build_team(rec, on_delegate=on_delegate)
    except Exception as exc:
        raise AgentUnavailable(f"could not build the agent team: {exc}") from exc

    try:
        result = team["Boss"].run_sync(_brief(ticket), usage_limits=RUN_LIMITS).output
    except Exception as exc:
        raise AgentUnavailable(str(exc)) from exc

    if not isinstance(result, TicketResolution):
        raise AgentUnavailable("Boss did not return a structured resolution")

    # The Boss's own closing event. Tools it called directly, minus anything
    # already attributed to a teammate, are whatever is left on the recorder.
    emit("Boss", "Close out", result.summary)

    pending = _verify_payment(result, ticket, rec, money, days_until, emit)

    # The agents are a live model, so "no payment needed" is a claim, not a fact.
    # If the ticket still has an unmet obligation in the database, the backend
    # raises it itself rather than letting the ticket close over the top of it.
    if pending is None:
        pending = _catch_missed_obligation(ticket, rec, money, emit)

    return events, pending


def _catch_missed_obligation(ticket, rec, money, emit):
    """
    Re-check the ticket's own links against the database. A customer order whose
    linked invoice is still open, or a rent notice whose lease is unpaid, cannot
    be finished no matter what the team concluded.
    """
    kind = ref = payee = detail = None

    if ticket["invoice_id"]:
        for v in rec.call("get_vendors")["vendors"]:
            for inv in rec.call("get_open_invoices_for_vendor",
                                vendor_id=v["id"]).get("open_invoices", []):
                if inv["id"] == ticket["invoice_id"]:
                    kind, ref, payee = "vendor_payment", inv["id"], v["name"]
                    amount = inv["amount"]
                    detail = (f"invoice {inv['id']} to {v['name']} is still open, and they will "
                              f"not ship while it is")
                    break
            if kind:
                break

    if kind is None and ticket["lease_id"]:
        lease = rec.call("get_lease_details", lease_id=ticket["lease_id"])
        if lease.get("found"):
            kind, ref, payee = "rent_payment", lease["id"], lease["landlord"]
            amount = lease["monthly_rent"]
            detail = f"{lease['space_name']} rent for {lease['next_due']} has not been paid"

    if kind is None:
        return None

    balance = rec.call("get_cash_balance")["balance"]
    emit("Accounting", "Catch missed obligation",
         f"The team closed this ticket without raising a payment, but {detail}. "
         f"Holding the ticket open and preparing {money(amount)} for a human instead.",
         status="flagged")

    if balance < amount:
        emit("Accounting", "Refuse payment",
             f"{money(amount)} is needed but checking holds {money(balance)}. Refusing rather "
             f"than overdrawing.", status="refused")
        return None

    return {
        "kind": kind, "ref_id": ref, "amount": amount, "ticket_id": ticket["id"],
        "payee": payee, "reason": detail.capitalize() + ".",
        "balance_after": balance - amount, "amount_corrected": False,
        "raised_by_backend": True,
    }


def _verify_payment(result: TicketResolution, ticket, rec, money, days_until, emit):
    """
    Re-read any proposed payment from the database. The model's figure is a
    proposal; the database is the authority.
    """
    if not result.needs_payment:
        return None
    if not result.payment_kind or result.payment_ref_id is None:
        emit("Accounting", "Hold payment",
             "A payment was proposed without a kind or a reference, so there is nothing to "
             "verify. Escalating to a human rather than guessing.", status="refused", tools=[])
        return None

    kind, ref = result.payment_kind, int(result.payment_ref_id)

    if kind == "rent_payment":
        lease = rec.call("get_lease_details", lease_id=ref)
        if not lease.get("found"):
            emit("Accounting", "Hold payment",
                 f"Lease {ref} is not in the database, so no rent payment is prepared.",
                 status="refused")
            return None
        true_amount, payee = lease["monthly_rent"], lease["landlord"]
        detail = f"{lease['space_name']} rent due {lease['next_due']}"
    else:
        vendors = rec.call("get_vendors")["vendors"]
        found, payee = None, None
        for v in vendors:
            owed = rec.call("get_open_invoices_for_vendor", vendor_id=v["id"])
            for inv in owed.get("open_invoices", []):
                if inv["id"] == ref:
                    found, payee = inv, v["name"]
                    break
            if found:
                break
        if not found:
            emit("Accounting", "Hold payment",
                 f"Invoice {ref} is not open in the database, so no payment is prepared.",
                 status="refused")
            return None
        true_amount = found["amount"]
        detail = f"invoice {ref} to {payee} ({found['description']})"

    balance = rec.call("get_cash_balance")["balance"]

    proposed = result.payment_amount
    corrected = proposed is not None and abs(float(proposed) - true_amount) > 0.005
    note = ""
    if corrected:
        note = (f" The team proposed {money(float(proposed))}; the database says "
                f"{money(true_amount)}, so the database figure is used.")

    if balance < true_amount:
        emit("Accounting", "Refuse payment",
             f"{detail} needs {money(true_amount)} but checking holds {money(balance)}. "
             f"Refusing rather than overdrawing.{note}", status="refused")
        return None

    emit("Accounting", "Prepare payment",
         f"Verified against the database: {detail}, {money(true_amount)}. Checking holds "
         f"{money(balance)}, leaving {money(balance - true_amount)}. Waiting on a human."
         f"{note}",
         math=[
             {"label": "Payment", "value": money(true_amount)},
             {"label": "Checking balance now", "value": money(balance)},
             {"label": "Less this payment", "value": f"- {money(true_amount)}"},
             {"label": "Balance after", "value": money(balance - true_amount), "total": True},
         ])

    return {
        "kind": kind,
        "ref_id": ref,
        "amount": true_amount,
        "ticket_id": ticket["id"],
        "payee": payee,
        "reason": (result.reason or detail).strip(),
        "balance_after": balance - true_amount,
        "amount_corrected": corrected,
    }
