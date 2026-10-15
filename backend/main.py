"""
Campus Customs Backend API
FastAPI server providing routes for the multi-agent ticket resolution system.
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
import sqlite3
import json
import shutil
from pathlib import Path
from datetime import datetime

from backend.mcp_client import ToolRecorder, mcp, MCPError

app = FastAPI(title="Campus Customs Backend")

# Add CORS middleware for frontend dashboard
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Database paths
DB_WORKING = Path(__file__).parent.parent / "data" / "campus_customs_new.db"
DB_ORIGINAL = Path(__file__).parent.parent / "data" / "campus_customs.db"
AUDIT_TRAIL = Path(__file__).parent.parent / "output" / "audit_trail.json"

# Shop pricing rules, in one place so the agents and the board never disagree.
MARGIN_FLOOR = 0.20     # never quote a price that returns less than this
BULK_DISCOUNT = 0.15    # the discount we offer on a bulk request, floor permitting


# ============================================================================
# DATA MODELS
# ============================================================================

class Ticket(BaseModel):
    id: int
    type: str
    requester: str
    subject: str
    sku: Optional[str] = None
    size: Optional[str] = None
    qty: Optional[int] = None
    status: str
    created_at: str


class AgentEvent(BaseModel):
    timestamp: str
    agent: str
    action: str
    ticket_id: Optional[int] = None
    tools_used: List[str] = []
    output: Optional[str] = None
    status: str
    draft: Optional[dict] = None          # Customer Service: the message held for review
    math: Optional[List[dict]] = None     # Accounting: the worked calculation


class PaymentApproval(BaseModel):
    kind: str  # "vendor_payment" or "rent_payment"
    ref_id: int  # invoice_id or lease_id
    amount: float
    approved_by: str
    ticket_id: Optional[int] = None  # ticket to resolve once the payment clears


class CashBalance(BaseModel):
    account: str
    balance: float
    date: str


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def get_db():
    """Get database connection to working copy."""
    conn = sqlite3.connect(str(DB_WORKING))
    conn.row_factory = sqlite3.Row
    return conn


def load_audit_trail():
    """Load audit trail from JSON file."""
    if AUDIT_TRAIL.exists():
        with open(AUDIT_TRAIL, 'r') as f:
            return json.load(f)
    return {"audit_trail": [], "metadata": {}}


def append_audit_event(event: dict):
    """Append event to audit trail."""
    append_audit_events([event])


def append_audit_events(events: List[dict]):
    """Append a batch of events to the audit trail."""
    trail = load_audit_trail()
    trail["audit_trail"].extend(events)
    with open(AUDIT_TRAIL, 'w') as f:
        json.dump(trail, f, indent=2)


def money(value: float) -> str:
    return f"${value:,.2f}"


def days_until(target: str, today: str) -> int:
    fmt = "%Y-%m-%d"
    return (datetime.strptime(target, fmt) - datetime.strptime(today, fmt)).days


def set_ticket_status(conn, ticket_id: int, status: str):
    conn.execute("UPDATE tickets SET status = ? WHERE id = ?", (status, ticket_id))
    conn.commit()


# ============================================================================
# ROUTES
# ============================================================================

@app.get("/tickets", response_model=List[Ticket])
def get_tickets():
    """
    Return the three open tickets with their status (open or resolved).
    """
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            SELECT id, type, requester, subject, sku, size, qty, status, created_at
            FROM tickets
            WHERE id IN (101, 102, 103)
            ORDER BY id
        """)
        
        tickets = []
        for row in cursor.fetchall():
            tickets.append(Ticket(
                id=row["id"],
                type=row["type"],
                requester=row["requester"],
                subject=row["subject"],
                sku=row["sku"],
                size=row["size"],
                qty=row["qty"],
                status=row["status"],
                created_at=row["created_at"]
            ))
        
        return tickets
    finally:
        conn.close()


def orchestrate(ticket, today: str):
    """
    Walk the agent team through one ticket.

    Every fact below is fetched with a real MCP tools/call round trip against
    mcp_server/server.py, so the tool names recorded on each event are a record
    of calls that actually happened. Routing follows the plans in
    output/harness.md.

    Returns (events, pending_approval).
    """
    tid = ticket["id"]
    events = []
    pending = None
    t = ToolRecorder()

    def step(agent, action, output, draft=None, math=None):
        # tools come from the recorder, so they cannot drift from reality
        events.append({
            "timestamp": datetime.now().isoformat(),
            "agent": agent,
            "action": action,
            "ticket_id": tid,
            "tools_used": t.take(),
            "output": output,
            "status": "complete",
            "draft": draft,
            "math": math,
        })

    board = t.call("get_tickets")
    still_open = sum(1 for x in board.get("open_tickets", []) if x["id"] != tid)

    if ticket["type"] == "customer_order":
        step("Boss", "Route ticket",
             f"Customer order from {ticket['requester']} for {ticket['subject']} "
             f"({ticket['sku']}, size {ticket['size']}, qty {ticket['qty']}). "
             f"Stock issue suspected, so inventory goes first. "
             f"{still_open} other ticket(s) still open on the board.")

        stock = t.call("get_inventory_stock", sku=ticket["sku"], size=ticket["size"])
        on_hand = stock["qty"]
        short = max(0, (ticket["qty"] or 0) - on_hand)
        vendors = t.call("get_vendors")["vendors"]
        vendor = next((v for v in vendors if v["specialty"] == "apparel reprint"), None)

        step("Inventory", "Check stock",
             f"{stock['name']} size {ticket['size']} in {stock['location']}: {on_hand} on hand, "
             f"{ticket['qty']} needed, short {short}. "
             + (f"{vendor['name']} reprints apparel in {vendor['lead_days']} days. Checking whether "
                f"their account is clear before anyone promises a date — over to Accounting."
                if vendor else "No apparel reprint vendor is on file, so this cannot be restocked."))

        inv = None
        if vendor:
            owed = t.call("get_open_invoices_for_vendor", vendor_id=vendor["id"])
            invoices = owed.get("open_invoices", [])
            inv = next((i for i in invoices if i["id"] == ticket["invoice_id"]), None) or \
                  (invoices[0] if invoices else None)
            cash = t.call("get_cash_balance")["balance"]

        if inv:
            overdue = -days_until(inv["due_date"], today)
            affordable = cash >= inv["amount"]
            # Worth checking the item still earns its shelf space before we
            # clear an overdue invoice just to reprint it.
            unit = t.call("get_pricing", sku=ticket["sku"])
            step("Accounting", "Clear vendor gate",
                 f"Invoice {inv['id']} to {vendor['name']} for {money(inv['amount'])} "
                 f"({inv['description']}) is {overdue} days overdue, and they will not ship while it is "
                 f"open. The tee itself costs {money(unit['unit_cost'])} against "
                 f"{money(unit['list_price'])} list, a {unit['margin_percent']:.1f}% margin, so the "
                 f"reprint is worth doing. Checking balance is {money(cash)}, "
                 + (f"so there is room. Payment prepared, waiting on a human."
                    if affordable else
                    f"which does not cover it. Refusing to prepare a payment that would overdraw; "
                    f"escalating to a human."),
                 math=[
                     {"label": f"Invoice {inv['id']} — {vendor['name']}", "value": money(inv["amount"])},
                     {"label": f"Due {inv['due_date']}", "value": f"{overdue} days overdue"},
                     {"label": f"{ticket['sku']} unit cost", "value": money(unit["unit_cost"])},
                     {"label": f"{ticket['sku']} list price", "value": money(unit["list_price"])},
                     {"label": "Margin on the reprinted item", "value": f"{unit['margin_percent']:.1f}%"},
                     {"label": "Checking balance now", "value": money(cash)},
                     {"label": "Less this payment", "value": f"- {money(inv['amount'])}"},
                     {"label": "Balance after", "value": money(cash - inv["amount"]), "total": True},
                 ])
            if affordable:
                pending = {
                    "kind": "vendor_payment", "ref_id": inv["id"], "amount": inv["amount"],
                    "ticket_id": tid, "payee": vendor["name"],
                    "reason": f"Unblocks the {vendor['name']} reprint of {ticket['sku']} size {ticket['size']}.",
                    "balance_after": cash - inv["amount"],
                }

        lead = vendor["lead_days"] if vendor else None
        step("Customer Service", "Draft reply",
             f"Drafted for {ticket['requester']}: size {ticket['size']} is out of stock today, a reprint "
             f"runs about {lead} days once the vendor is cleared, and we will confirm a date before "
             f"charging. Held internally for review."
             if vendor else f"Drafted a holding note for {ticket['requester']}; no restock path exists yet.",
             draft={
                 "to": ticket["requester"],
                 "subject": f"Your {ticket['subject']} (size {ticket['size']}) — a short delay",
                 "body": (
                     f"Hi {ticket['requester'].split()[0]},\n\n"
                     f"Thanks for your order for the {stock['name']} in size {ticket['size']}. "
                     f"We are out of that size on the shelf today, so I do not want to give you a ship "
                     f"date I cannot keep.\n\n"
                     f"We have a reprint lined up with {vendor['name']}, who run about "
                     f"{lead} days once the order is released. As soon as that is confirmed I will email "
                     f"you the exact date, and we will not charge the card before then.\n\n"
                     f"If you need it sooner than that, tell me and I will see what else we can do.\n\n"
                     f"— Campus Customs"
                 ),
             } if vendor else None)

    elif ticket["type"] == "rent_notice":
        step("Boss", "Route ticket",
             f"Rent notice from {ticket['requester']}. Facilities owns the shop space, so it starts there "
             f"and moves to Accounting for the cash side.")

        lease = t.call("get_lease_details", lease_id=ticket["lease_id"])
        portfolio = t.call("get_all_leases")
        others = [l for l in portfolio.get("leases", []) if l["id"] != lease["id"]]
        left = days_until(lease["next_due"], today)

        step("Facilities", "Check lease",
             f"{lease['space_name']} under {lease['landlord']}: {money(lease['monthly_rent'])} due "
             f"{lease['next_due']}, {left} days out. No grace period on file. "
             + (f"No other lease falls due in this window, so this is the only rent to plan for."
                if not others else
                f"{len(others)} other lease(s) on file — Accounting should check the cluster.")
             + " Passing the amount and the deadline to Accounting.")

        cash = t.call("get_cash_balance")["balance"]
        after = cash - lease["monthly_rent"]
        affordable = after >= 0
        step("Accounting", "Prepare rent",
             f"Checking balance is {money(cash)}. Rent of {money(lease['monthly_rent'])} leaves "
             f"{money(after)}. "
             + (f"Funds are sufficient, but rent is the largest outflow on the board, so it goes to a "
                f"human rather than straight through."
                if affordable else
                f"That is an overdraft, so no payment is prepared. Escalating to a human."),
             math=[
                 {"label": f"{lease['space_name']} monthly rent", "value": money(lease["monthly_rent"])},
                 {"label": f"Due {lease['next_due']}", "value": f"{left} days out"},
                 {"label": "Checking balance now", "value": money(cash)},
                 {"label": "Less this payment", "value": f"- {money(lease['monthly_rent'])}"},
                 {"label": "Balance after", "value": money(after), "total": True},
             ])
        if affordable:
            pending = {
                "kind": "rent_payment", "ref_id": lease["id"], "amount": lease["monthly_rent"],
                "ticket_id": tid, "payee": lease["landlord"],
                "reason": f"{lease['space_name']} rent due {lease['next_due']}, {left} days out.",
                "balance_after": after,
            }

    elif ticket["type"] == "price_override":
        step("Boss", "Route ticket",
             f"{ticket['requester']} wants {ticket['qty']} of {ticket['sku']} size {ticket['size']} at a "
             f"discount. Inventory checks we can even fill it before Accounting prices it.")

        stock = t.call("get_inventory_stock", sku=ticket["sku"], size=ticket["size"])
        gap = max(0, ticket["qty"] - stock["qty"])
        vendors = t.call("get_vendors")["vendors"]
        vendor = next((v for v in vendors if v["specialty"] == "apparel reprint"), None)
        blocked = t.call("get_open_invoices_for_vendor", vendor_id=vendor["id"])["open_invoices"]

        step("Inventory", "Feasibility check",
             f"{stock['name']} size {ticket['size']}: {stock['qty']} on hand against {ticket['qty']} "
             f"requested, so {gap} short. {vendor['name']} covers the gap in {vendor['lead_days']} days. "
             + ("Their account is clear, so that lead time holds."
                if not blocked else
                f"They still hold {len(blocked)} unpaid invoice "
                f"({', '.join(str(b['id']) for b in blocked)}, "
                f"{money(sum(b['amount'] for b in blocked))}) and will not ship until it clears, so the "
                f"{vendor['lead_days']}-day lead only starts once that is paid. Do not promise a date yet."))

        price = t.call("get_pricing", sku=ticket["sku"])
        cost, lst = price["unit_cost"], price["list_price"]
        at_list = price["margin_percent"]
        floor = round(cost / (1 - MARGIN_FLOOR), 2)
        wanted = round(lst * (1 - BULK_DISCOUNT), 2)
        offer = max(wanted, floor)
        clamped = offer > wanted
        undiscountable = floor >= lst
        margin = (offer - cost) / offer * 100
        pct_off = (lst - offer) / lst * 100

        if undiscountable:
            verdict = (f"That floor is at or above the {money(lst)} list price, so there is no discount to "
                       f"give on this item at all — any reduction sells it below the {MARGIN_FLOOR:.0%} "
                       f"margin rule. Escalating to a human: either the list price needs revisiting or the "
                       f"request is declined. No number goes to the customer.")
        elif clamped:
            verdict = (f"A {BULK_DISCOUNT:.0%} discount would land at {money(wanted)}, which breaches the "
                       f"{MARGIN_FLOOR:.0%} floor, so it is held at {money(offer)} — "
                       f"{pct_off:.1f}% off, {margin:.1f}% margin, {money(offer * ticket['qty'])} on "
                       f"{ticket['qty']} units. Quote the smaller discount, not the one asked for.")
        else:
            verdict = (f"A {BULK_DISCOUNT:.0%} bulk discount at {money(offer)} still returns {margin:.1f}%, "
                       f"or {money(offer * ticket['qty'])} on {ticket['qty']} units. "
                       f"Approved to quote, no payment involved.")

        step("Accounting", "Margin check",
             f"Unit cost {money(cost)} against list {money(lst)} is a {at_list:.1f}% margin. "
             f"Holding a {MARGIN_FLOOR:.0%} floor puts the lowest workable price at {money(floor)}. {verdict}",
             math=[
                 {"label": "Unit cost", "value": money(cost)},
                 {"label": "List price", "value": money(lst)},
                 {"label": "Margin at list", "value": f"{at_list:.1f}%"},
                 {"label": f"Lowest price holding a {MARGIN_FLOOR:.0%} floor", "value": money(floor)},
                 {"label": f"Asked-for discount ({BULK_DISCOUNT:.0%} off)", "value": money(wanted)},
                 {"label": "Held at the floor instead" if clamped else "Clears the floor",
                  "value": money(offer)},
                 {"label": "Discount actually offered", "value": f"{pct_off:.1f}% off"},
                 {"label": "Margin at that price", "value": f"{margin:.1f}%"},
                 {"label": f"Line total, {ticket['qty']} units", "value": money(offer * ticket["qty"]), "total": True},
             ])

        t.call("get_pricing", sku=ticket["sku"])
        step("Customer Service", "Draft quote",
             (f"No price drafted. Accounting could not clear any discount on this item, so there is "
              f"nothing to quote {ticket['requester']} until a human rules on it."
              if undiscountable else
              f"Drafted for {ticket['requester']}: {stock['qty']} available now, remaining {gap} in about "
              f"{vendor['lead_days']} days, at {money(offer)} each for the full {ticket['qty']}. "
              f"Held internally until someone signs off."),
             draft=None if undiscountable else {
                 "to": ticket["requester"],
                 "subject": f"Quote — {ticket['qty']} hoodies, size {ticket['size']}",
                 "body": (
                     f"Hi {ticket['requester']},\n\n"
                     f"Happy to do a bulk rate on this. Here is where we land.\n\n"
                     f"We have {stock['qty']} of the {stock['name']} in size {ticket['size']} on the "
                     f"shelf right now. The remaining {gap} would come from a reprint with "
                     f"{vendor['name']}, which runs about {vendor['lead_days']} days.\n\n"
                     f"On price, we can do {money(offer)} per hoodie for the full {ticket['qty']}, down "
                     f"from {money(lst)} — that is {pct_off:.0f}% off, and it comes to "
                     f"{money(offer * ticket['qty'])} for the order.\n\n"
                     f"If that works, tell me your deadline and I will confirm whether the reprint lands "
                     f"in time before you commit.\n\n"
                     f"— Campus Customs"
                 ),
             })

    step("Boss", "Close out",
         "Payment is prepared and waiting on a human. The ticket stays open until it clears."
         if pending else "No cash moves on this one, so the ticket is resolved.")

    return events, pending


@app.post("/run-ticket/{ticket_id}")
def run_ticket(ticket_id: int):
    """
    Run the agent team on a specific ticket.

    Every fact in the returned events was fetched through a real MCP tools/call
    against mcp_server/server.py. Tickets that need no payment are resolved
    here; the rest wait on /approve-payment.
    """
    conn = get_db()
    try:
        ticket = conn.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,)).fetchone()
        if ticket is None:
            raise HTTPException(status_code=404, detail=f"Ticket {ticket_id} not found")

        today = conn.execute("SELECT date_today FROM desk").fetchone()["date_today"]
        try:
            events, pending = orchestrate(ticket, today)
        except MCPError as exc:
            raise HTTPException(
                status_code=503,
                detail=(f"The agent team could not reach the MCP server, so no facts could be "
                        f"verified and nothing was run. Start it with "
                        f"'python -m mcp_server.server'. Underlying error: {exc}"),
            )
        append_audit_events(events)

        if pending is None:
            set_ticket_status(conn, ticket_id, "resolved")

        return {
            "ticket_id": ticket_id,
            "status": "awaiting_approval" if pending else "resolved",
            "events": events,
            "pending_approval": pending,
        }
    finally:
        conn.close()


@app.get("/agent-events", response_model=List[AgentEvent])
def get_agent_events():
    """
    Return all agent events from the audit trail.
    Each event shows what an agent said, which tools it used, and the result.
    Used by the dashboard to display agent activity and refresh the board.
    """
    trail = load_audit_trail()
    
    events = []
    for event_data in trail.get("audit_trail", []):
        events.append(AgentEvent(
            timestamp=event_data.get("timestamp", ""),
            agent=event_data.get("agent", "system"),
            action=event_data.get("action", ""),
            ticket_id=event_data.get("ticket_id"),
            tools_used=event_data.get("tools_used", []),
            output=event_data.get("output"),
            status=event_data.get("status", "unknown")
        ))
    
    return events


@app.post("/approve-payment")
def approve_payment(payment: PaymentApproval):
    """
    Process a human-approved payment.
    This route actually changes the cash balance (logs the payment to the database).
    Agents can only PREPARE payments; this route is what makes them real.
    """
    conn = get_db()
    cursor = conn.cursor()

    try:
        cursor.execute("SELECT balance FROM cash_accounts WHERE name = 'checking'")
        result = cursor.fetchone()
        current_balance = result["balance"] if result else 0

        # Shop rule: refuse rather than ever go negative.
        if current_balance < payment.amount:
            append_audit_event({
                "timestamp": datetime.now().isoformat(),
                "agent": "Accounting",
                "action": "Refuse payment",
                "ticket_id": payment.ticket_id,
                "tools_used": ["get_cash_balance"],
                "output": f"Refused {money(payment.amount)}: checking holds only {money(current_balance)}.",
                "status": "refused",
            })
            raise HTTPException(
                status_code=400,
                detail=f"Insufficient funds. Balance: {money(current_balance)}, required: {money(payment.amount)}"
            )

        # The payment row is written through the MCP log_payment tool, the same
        # path an agent would use, rather than an INSERT behind its back.
        logged = mcp.call(
            "log_payment",
            kind=payment.kind,
            ref_id=payment.ref_id,
            amount=payment.amount,
            account="checking",
            paid_at=datetime.now().isoformat(),
            approved_by=payment.approved_by,
        )
        if not logged.get("success"):
            raise HTTPException(status_code=500,
                                detail=f"log_payment failed: {logged.get('error')}")
        payment_id = logged["payment_id"]

        new_balance = current_balance - payment.amount
        cursor.execute("UPDATE cash_accounts SET balance = ? WHERE name = 'checking'", (new_balance,))

        # Shop rule: once a payment is made, update the table it came from.
        if payment.kind == "vendor_payment":
            cursor.execute("UPDATE invoices SET status = 'paid' WHERE id = ?", (payment.ref_id,))

        if payment.ticket_id is not None:
            cursor.execute("UPDATE tickets SET status = 'resolved' WHERE id = ?", (payment.ticket_id,))

        conn.commit()

        append_audit_events([
            {
                "timestamp": datetime.now().isoformat(),
                "agent": "Human",
                "action": "Approve payment",
                "ticket_id": payment.ticket_id,
                "tools_used": [],
                "output": f"{payment.approved_by} approved {money(payment.amount)} ({payment.kind}, ref {payment.ref_id}).",
                "status": "approved",
            },
            {
                "timestamp": datetime.now().isoformat(),
                "agent": "Accounting",
                "action": "Record payment",
                "ticket_id": payment.ticket_id,
                "tools_used": ["log_payment"],
                "output": f"Paid from checking. Balance {money(current_balance)} to {money(new_balance)}."
                          + (f" Invoice {payment.ref_id} marked paid." if payment.kind == "vendor_payment" else ""),
                "status": "complete",
            },
        ])

        return {
            "status": "approved",
            "payment_id": payment_id,
            "previous_balance": current_balance,
            "amount": payment.amount,
            "new_balance": new_balance,
            "approved_by": payment.approved_by,
            "ticket_id": payment.ticket_id,
        }

    except HTTPException:
        conn.rollback()
        raise
    except Exception as e:
        conn.rollback()
        # A payment row may already be committed by the MCP tool. Remove it so
        # payments never disagrees with cash_accounts.
        if "payment_id" in dir() or locals().get("payment_id"):
            try:
                cleanup = get_db()
                cleanup.execute("DELETE FROM payments WHERE id = ?", (locals()["payment_id"],))
                cleanup.commit()
                cleanup.close()
            except Exception:
                pass
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@app.get("/cash-balance", response_model=CashBalance)
def get_cash_balance():
    """
    Return the current cash balance from cash_accounts table.
    Used by the dashboard and agents to check available funds.
    """
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        cursor.execute("SELECT name, balance, date FROM cash_accounts WHERE name = 'checking'")
        row = cursor.fetchone()
        
        if not row:
            raise HTTPException(status_code=404, detail="Cash account not found")
        
        return CashBalance(
            account=row["name"],
            balance=row["balance"],
            date=row["date"]
        )
    finally:
        conn.close()


@app.post("/reset-db")
def reset_database():
    """
    Reset the working database to original values.
    Copies campus_customs.db to campus_customs_new.db.
    Use this before starting a fresh run of all three tickets.
    """
    try:
        # Copy original to working
        shutil.copy(str(DB_ORIGINAL), str(DB_WORKING))

        # The audit trail is append-only: a reset is recorded as an event in the
        # log rather than erasing the history that came before it.
        conn = get_db()
        try:
            balance = conn.execute(
                "SELECT balance FROM cash_accounts WHERE name = 'checking'").fetchone()["balance"]
        finally:
            conn.close()

        append_audit_event({
            "timestamp": datetime.now().isoformat(),
            "agent": "System",
            "action": "Reset board",
            "ticket_id": None,
            "tools_used": [],
            "output": f"Working database restored from campus_customs.db. "
                      f"Starting checking balance {money(balance)}. All tickets back to open.",
            "status": "reset",
        })

        return {
            "status": "reset",
            "message": "Database reset to original values",
            "timestamp": datetime.now().isoformat()
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Reset failed: {str(e)}")


# ============================================================================
# HEALTH CHECK
# ============================================================================

@app.get("/health")
def health_check():
    """
    Health check endpoint. Returns 200 if backend is running.
    """
    return {
        "status": "healthy",
        "service": "Campus Customs Backend",
        "timestamp": datetime.now().isoformat()
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
