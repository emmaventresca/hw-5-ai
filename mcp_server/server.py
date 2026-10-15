#!/usr/bin/env python3
"""
Campus Customs MCP Server

Nine read/write tools over data/campus_customs_new.db, exposed over the MCP
stdio transport as JSON-RPC 2.0. Implemented against the wire protocol directly
so the server runs with no third-party dependencies.
"""

import sqlite3
import json
import sys
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "campus_customs_new.db"


def get_inventory_stock(sku: str, size: str) -> dict:
    """Query current inventory qty for SKU + size."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute(
        "SELECT name, qty, location FROM inventory WHERE sku = ? AND size = ?",
        (sku, size)
    )
    row = cursor.fetchone()
    conn.close()
    
    if row:
        return {
            "sku": sku,
            "name": row["name"],
            "size": size,
            "qty": row["qty"],
            "location": row["location"],
            "found": True
        }
    else:
        return {
            "sku": sku,
            "name": None,
            "size": size,
            "qty": 0,
            "location": None,
            "found": False
        }


def get_open_invoices_for_vendor(vendor_id: int) -> dict:
    """Query all open invoices for a specific vendor."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute(
        """
        SELECT id, vendor_id, amount, due_date, status, description 
        FROM invoices 
        WHERE vendor_id = ? AND status = 'open'
        ORDER BY due_date
        """,
        (vendor_id,)
    )
    rows = cursor.fetchall()
    conn.close()
    
    invoices = []
    for row in rows:
        invoices.append({
            "id": row["id"],
            "vendor_id": row["vendor_id"],
            "amount": row["amount"],
            "due_date": row["due_date"],
            "status": row["status"],
            "description": row["description"]
        })
    
    return {
        "vendor_id": vendor_id,
        "open_invoices": invoices,
        "total_amount_due": sum(inv["amount"] for inv in invoices)
    }


def get_lease_details(lease_id: int) -> dict:
    """Query lease details by ID."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute(
        """
        SELECT id, space_name, landlord, monthly_rent, next_due, notes 
        FROM leases 
        WHERE id = ?
        """,
        (lease_id,)
    )
    row = cursor.fetchone()
    conn.close()
    
    if row:
        return {
            "id": row["id"],
            "space_name": row["space_name"],
            "landlord": row["landlord"],
            "monthly_rent": row["monthly_rent"],
            "next_due": row["next_due"],
            "notes": row["notes"],
            "found": True
        }
    else:
        return {
            "id": lease_id,
            "found": False
        }


def get_tickets() -> dict:
    """Get all open tickets from the board."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute(
        """
        SELECT id, type, requester, subject, sku, size, qty, lease_id, invoice_id, status, created_at
        FROM tickets 
        WHERE status = 'open'
        ORDER BY created_at
        """
    )
    rows = cursor.fetchall()
    conn.close()
    
    tickets = []
    for row in rows:
        tickets.append({
            "id": row["id"],
            "type": row["type"],
            "requester": row["requester"],
            "subject": row["subject"],
            "sku": row["sku"],
            "size": row["size"],
            "qty": row["qty"],
            "lease_id": row["lease_id"],
            "invoice_id": row["invoice_id"],
            "status": row["status"],
            "created_at": row["created_at"]
        })
    
    return {"open_tickets": tickets, "total": len(tickets)}


def get_vendors() -> dict:
    """Get all vendors with their lead times and specialties."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute(
        "SELECT id, name, specialty, lead_days FROM vendors ORDER BY id"
    )
    rows = cursor.fetchall()
    conn.close()
    
    vendors = []
    for row in rows:
        vendors.append({
            "id": row["id"],
            "name": row["name"],
            "specialty": row["specialty"],
            "lead_days": row["lead_days"]
        })
    
    return {"vendors": vendors, "total": len(vendors)}


def get_cash_balance() -> dict:
    """Get current cash account balance."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute(
        "SELECT name, balance, date FROM cash_accounts WHERE name = 'checking'"
    )
    row = cursor.fetchone()
    conn.close()
    
    if row:
        return {
            "account": row["name"],
            "balance": row["balance"],
            "date": row["date"]
        }
    else:
        return {"error": "No checking account found"}


def get_all_leases() -> dict:
    """Get all leases with their due dates."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute(
        "SELECT id, space_name, landlord, monthly_rent, next_due, notes FROM leases ORDER BY next_due"
    )
    rows = cursor.fetchall()
    conn.close()
    
    leases = []
    for row in rows:
        leases.append({
            "id": row["id"],
            "space_name": row["space_name"],
            "landlord": row["landlord"],
            "monthly_rent": row["monthly_rent"],
            "next_due": row["next_due"],
            "notes": row["notes"]
        })
    
    return {"leases": leases, "total": len(leases)}


def get_pricing(sku: str) -> dict:
    """Get pricing for a specific SKU."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute(
        "SELECT sku, unit_cost, list_price FROM pricing WHERE sku = ?",
        (sku,)
    )
    row = cursor.fetchone()
    conn.close()
    
    if row:
        return {
            "sku": row["sku"],
            "unit_cost": row["unit_cost"],
            "list_price": row["list_price"],
            "margin": row["list_price"] - row["unit_cost"],
            # Margin is measured against the selling price. Dividing by cost
            # gives markup, which is a much larger number and will mis-price
            # a discount if an agent treats it as margin.
            "margin_percent": ((row["list_price"] - row["unit_cost"]) / row["list_price"] * 100) if row["list_price"] > 0 else 0,
            "markup_percent": ((row["list_price"] - row["unit_cost"]) / row["unit_cost"] * 100) if row["unit_cost"] > 0 else 0,
            "found": True
        }
    else:
        return {"sku": sku, "found": False}


def log_payment(kind: str, ref_id: int, amount: float, account: str, paid_at: str, approved_by: str) -> dict:
    """Log an approved payment to the payments table."""
    try:
        conn = sqlite3.connect(str(DB_PATH))
        cursor = conn.cursor()
        
        cursor.execute(
            """
            INSERT INTO payments (kind, ref_id, amount, account, paid_at, approved_by)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (kind, ref_id, amount, account, paid_at, approved_by)
        )
        conn.commit()
        
        # Get the last inserted ID
        payment_id = cursor.lastrowid
        conn.close()
        
        return {
            "success": True,
            "payment_id": payment_id,
            "kind": kind,
            "amount": amount,
            "paid_at": paid_at,
            "approved_by": approved_by
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def get_desk_today() -> dict:
    """The shop's current date, used to decide what is overdue."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT date_today, notes FROM desk LIMIT 1")
    row = cursor.fetchone()
    conn.close()
    if row:
        return {"date_today": row["date_today"], "notes": row["notes"], "found": True}
    return {"found": False}

# ============================================================================
# MCP STDIO TRANSPORT
# ============================================================================

PROTOCOL_VERSION = "2024-11-05"

def _s(desc):   return {"type": "string", "description": desc}
def _i(desc):   return {"type": "integer", "description": desc}
def _n(desc):   return {"type": "number", "description": desc}

TOOLS = [
    {
        "name": "get_inventory_stock",
        "description": "Current on-hand quantity and aisle for a SKU in one size. "
                       "Use before promising a customer anything.",
        "fn": get_inventory_stock,
        "inputSchema": {"type": "object", "required": ["sku", "size"], "properties": {
            "sku": _s("Product SKU, e.g. CC-TEE-WHITE"),
            "size": _s("Size code, e.g. S, M, L, XL, OS")}},
    },
    {
        "name": "get_open_invoices_for_vendor",
        "description": "Unpaid invoices for one vendor. A vendor holding an open invoice "
                       "will not ship new product, so check this before quoting a lead time.",
        "fn": get_open_invoices_for_vendor,
        "inputSchema": {"type": "object", "required": ["vendor_id"], "properties": {
            "vendor_id": _i("Vendor id from the vendors table")}},
    },
    {
        "name": "get_lease_details",
        "description": "One lease: space, landlord, monthly rent and next due date.",
        "fn": get_lease_details,
        "inputSchema": {"type": "object", "required": ["lease_id"], "properties": {
            "lease_id": _i("Lease id from the leases table")}},
    },
    {
        "name": "get_desk_today",
        "description": "The shop's current date. Call this before judging whether an invoice "
                       "or a rent payment is overdue — never assume today's date.",
        "fn": get_desk_today,
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_tickets",
        "description": "Every ticket on the board with its status and linked invoice or lease.",
        "fn": get_tickets,
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_vendors",
        "description": "All vendors with their specialty and lead time in days.",
        "fn": get_vendors,
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_cash_balance",
        "description": "Current checking balance. Check before preparing any payment.",
        "fn": get_cash_balance,
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_all_leases",
        "description": "The full lease portfolio with due dates.",
        "fn": get_all_leases,
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_pricing",
        "description": "Unit cost and list price for a SKU, for margin work.",
        "fn": get_pricing,
        "inputSchema": {"type": "object", "required": ["sku"], "properties": {
            "sku": _s("Product SKU, e.g. CC-HOOD-NAVY")}},
    },
    {
        "name": "log_payment",
        "description": "Record a payment that a human has already approved. Agents must never "
                       "call this on their own initiative.",
        "fn": log_payment,
        "inputSchema": {"type": "object",
            "required": ["kind", "ref_id", "amount", "account", "paid_at", "approved_by"],
            "properties": {
                "kind": _s("vendor_payment or rent_payment"),
                "ref_id": _i("Invoice id or lease id the payment settles"),
                "amount": _n("Amount in dollars"),
                "account": _s("Account paid from, e.g. checking"),
                "paid_at": _s("ISO timestamp"),
                "approved_by": _s("Name of the human who approved it")}},
    },
]

BY_NAME = {t["name"]: t for t in TOOLS}


def _send(message):
    sys.stdout.write(json.dumps(message) + "\n")
    sys.stdout.flush()


def _result(request_id, payload):
    _send({"jsonrpc": "2.0", "id": request_id, "result": payload})


def _error(request_id, code, message):
    _send({"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}})


def _handle(request):
    method = request.get("method")
    request_id = request.get("id")

    if method == "initialize":
        _result(request_id, {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "campus_customs", "version": "1.0.0"},
        })
    elif method == "tools/list":
        _result(request_id, {"tools": [
            {k: t[k] for k in ("name", "description", "inputSchema")} for t in TOOLS]})
    elif method == "tools/call":
        params = request.get("params") or {}
        name = params.get("name")
        tool = BY_NAME.get(name)
        if tool is None:
            _error(request_id, -32602, f"Unknown tool: {name}")
            return
        try:
            value = tool["fn"](**(params.get("arguments") or {}))
            _result(request_id, {
                "content": [{"type": "text", "text": json.dumps(value, indent=2)}]})
        except Exception as exc:
            _result(request_id, {
                "content": [{"type": "text", "text": f"{type(exc).__name__}: {exc}"}],
                "isError": True})
    elif method == "ping":
        _result(request_id, {})
    elif request_id is not None:
        _error(request_id, -32601, f"Method not found: {method}")
    # notifications carry no id and need no reply


def main():
    if not DB_PATH.exists():
        print(f"Database not found at {DB_PATH}. Copy data/campus_customs.db to "
              f"data/campus_customs_new.db first.", file=sys.stderr)
        return 1
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
        except json.JSONDecodeError:
            continue
        _handle(request)
    return 0


if __name__ == "__main__":
    sys.exit(main())
