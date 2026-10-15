"""
Campus Customs Multi-Agent Backend
Five-agent team with full connectivity: Boss, Inventory, Accounting, Facilities, Customer Service.
All agents query data via MCP server (campus_customs_new.db).
All actions logged to output/audit_trail.json.
"""

from backend.models import (
    Ticket, InventoryItem, Pricing, Vendor, Lease, CashAccount,
    Invoice, Payment, Desk, AuditEvent, AGENTS
)

__all__ = [
    "Ticket", "InventoryItem", "Pricing", "Vendor", "Lease", "CashAccount",
    "Invoice", "Payment", "Desk", "AuditEvent", "AGENTS"
]
