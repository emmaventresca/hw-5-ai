"""
Data models for Campus Customs multi-agent system.
These models represent the shop's core entities queried via MCP tools.
"""

from dataclasses import dataclass
from typing import Optional, List
from datetime import datetime


@dataclass
class Ticket:
    """Open ticket on the board requiring agent action."""
    id: int
    type: str  # customer_order, rent_notice, price_override, payment_request, etc.
    requester: str
    subject: str
    sku: Optional[str] = None
    size: Optional[str] = None
    qty: Optional[int] = None
    lease_id: Optional[int] = None
    invoice_id: Optional[int] = None
    status: str = "open"
    notes: Optional[str] = None
    created_at: Optional[str] = None


@dataclass
class InventoryItem:
    """Current stock level for a SKU + size combination."""
    sku: str
    name: str
    size: str
    qty: int
    location: str


@dataclass
class Pricing:
    """Cost and pricing for a SKU."""
    sku: str
    unit_cost: float
    list_price: float


@dataclass
class Vendor:
    """Third-party vendor for restocking."""
    id: int
    name: str
    specialty: str  # e.g., "apparel reprint", "mugs and small goods", "local courier"
    lead_days: int  # days until delivery


@dataclass
class Lease:
    """Property lease agreement."""
    id: int
    space_name: str
    landlord: str
    monthly_rent: float
    next_due: str  # ISO date string
    notes: Optional[str] = None


@dataclass
class CashAccount:
    """Shop's cash account balance."""
    name: str  # e.g., "checking"
    balance: float
    date: str  # ISO date string


@dataclass
class Invoice:
    """Open invoice from a vendor."""
    id: int
    vendor_id: int
    amount: float
    due_date: str  # ISO date string
    status: str  # "open" or "paid"
    description: Optional[str] = None


@dataclass
class Payment:
    """Record of an approved payment."""
    id: int
    kind: str  # "vendor_payment", "rent_payment", etc.
    ref_id: Optional[int] = None  # invoice_id or lease_id
    amount: float = 0.0
    account: str = "checking"
    paid_at: Optional[str] = None  # ISO date string
    approved_by: str = "system"


@dataclass
class Desk:
    """Shop operations metadata."""
    date_today: str  # ISO date string - the shop's operational date
    notes: Optional[str] = None


# Agent team configuration
AGENTS = {
    "boss": {
        "name": "Boss",
        "role": "Ticket triage and delegation",
        "prompt_file": "backend/prompts/boss.md",
        "tools": ["get_tickets", "delegate_task", "close_ticket"]
    },
    "inventory": {
        "name": "Inventory",
        "role": "Stock management and vendor coordination",
        "prompt_file": "backend/prompts/inventory.md",
        "tools": ["get_inventory_stock", "get_vendors", "get_vendor_pricing"]
    },
    "accounting": {
        "name": "Accounting",
        "role": "Cash and payment management",
        "prompt_file": "backend/prompts/accounting.md",
        "tools": ["get_cash_balance", "get_open_invoices_for_vendor", "approve_payment", "log_payment"]
    },
    "facilities": {
        "name": "Facilities",
        "role": "Lease and rent obligations",
        "prompt_file": "backend/prompts/facilities.md",
        "tools": ["get_lease_details", "get_all_leases"]
    },
    "customer_service": {
        "name": "Customer Service",
        "role": "Customer communication drafts",
        "prompt_file": "backend/prompts/customer_service.md",
        "tools": ["draft_customer_response", "get_pricing"]
    }
}


# Audit trail event for logging agent actions
@dataclass
class AuditEvent:
    """Log entry for agent actions."""
    timestamp: str  # ISO datetime
    agent: str  # Agent name
    action: str  # Action performed
    ticket_id: Optional[int] = None
    input_data: Optional[dict] = None
    output_data: Optional[dict] = None
    status: str = "success"  # "success", "error", "waiting_approval"
    notes: Optional[str] = None
