# Campus Customs MCP Server

## Purpose
This MCP (Model Context Protocol) server provides tools for the multi-agent team to query and modify the Campus Customs shop database. Every agent—Boss, Inventory, Accounting, Facilities, and Customer Service—uses these tools to access real-time data needed to resolve customer tickets.

All agents operate with full connectivity: any agent can delegate tasks to any other agent for help.

## Database
- **File:** `data/campus_customs_new.db` (working copy)
- **Original:** `data/campus_customs.db` (pristine, never modified)
- **Strategy:** All agent modifications happen on the working copy. Reset before each run by copying the original.

---

## Nine MCP Tools

### Read-Only Tools (Query Data)

#### 1. `get_inventory_stock(sku, size)`
- **Tables:** inventory
- **Input:** SKU code and size
- **Output:** Current qty in stock, location, found flag
- **Used by:** Boss (route tickets), Inventory (stock checks), Customer Service (availability)
- **Example:** `get_inventory_stock("CC-TEE-WHITE", "S")` → `{"qty": 0, "location": "Aisle B", "found": true}`

#### 2. `get_open_invoices_for_vendor(vendor_id)`
- **Tables:** invoices
- **Input:** Vendor ID
- **Output:** List of open invoices, amounts, due dates, total amount due
- **Used by:** Accounting (payment tracking), Inventory (payment gates)
- **Example:** `get_open_invoices_for_vendor(1)` → `{"vendor_id": 1, "open_invoices": [...], "total_amount_due": 840.0}`

#### 3. `get_lease_details(lease_id)`
- **Tables:** leases
- **Input:** Lease ID
- **Output:** Space name, landlord, monthly rent, next due date
- **Used by:** Facilities (rent tracking), Accounting (payment approvals)
- **Example:** `get_lease_details(1)` → `{"space_name": "Chapel Street shop", "monthly_rent": 2400.0, "next_due": "2026-09-02"}`

#### 4. `get_tickets()`
- **Tables:** tickets
- **Input:** None
- **Output:** All open tickets with type, requester, subject, status
- **Used by:** Boss (triage and delegation)
- **Example:** Returns array of ticket objects with id, type, requester, subject, etc.

#### 5. `get_vendors()`
- **Tables:** vendors
- **Input:** None
- **Output:** All vendors with id, name, specialty, lead_days
- **Used by:** Inventory (vendor selection), Customer Service (delivery estimates)
- **Example:** Returns `[{"id": 1, "name": "Bulldog Print Co", "specialty": "apparel reprint", "lead_days": 5}, ...]`

#### 6. `get_cash_balance()`
- **Tables:** cash_accounts
- **Input:** None
- **Output:** Checking account balance and current date
- **Used by:** Accounting (payment feasibility), Facilities (rent payment checks)
- **Example:** `{"account": "checking", "balance": 3400.0, "date": "2026-08-31"}`

#### 7. `get_all_leases()`
- **Tables:** leases
- **Input:** None
- **Output:** All leases ordered by next due date
- **Used by:** Facilities (lease overview), Accounting (payment planning)
- **Example:** Returns array of all lease objects sorted by urgency

#### 8. `get_pricing(sku)`
- **Tables:** pricing
- **Input:** SKU code
- **Output:** Unit cost, list price, calculated margin, margin percentage
- **Used by:** Accounting (margin validation), Customer Service (pricing info)
- **Example:** `get_pricing("CC-HOOD-NAVY")` → `{"sku": "CC-HOOD-NAVY", "unit_cost": 22.0, "list_price": 58.0, "margin": 36.0, "margin_percent": 163.6}`

### Write Tool (Modification)

#### 9. `log_payment(kind, ref_id, amount, account, paid_at, approved_by)`
- **Tables:** payments (INSERT only)
- **Input:** Payment kind (vendor_payment, rent_payment), ref_id (invoice_id or lease_id), amount, account, paid_at date, approved_by (human name)
- **Output:** Success flag, payment_id, confirmation details
- **Used by:** Accounting (record human-approved payments only)
- **Constraint:** Only called AFTER human approval; never auto-approves
- **Example:** `log_payment("rent_payment", 1, 2400.0, "checking", "2026-08-31", "Emma")` → `{"success": true, "payment_id": 42, ...}`

---

## Safety Guardrails

### Operational Limits
- **No Auto-Approval:** All payment-related writes require explicit human approval first
- **Token Budget:** $1–$2 per ticket resolution (gpt-luna-6 only)
- **Database Integrity:** Only `payments` table receives INSERT operations; no DELETE or UPDATE
- **Audit Trail:** Every agent action logged to `output/audit_trail.json` (append only)

### Data Privacy & Security
- **No Biometric Data:** Fingerprints, facial recognition, health info never processed
- **No Government IDs:** SSNs, passport numbers, driver's license info excluded
- **No Financial Secrets:** Credit card numbers, bank account numbers never logged
- **No Personal Contact Info:** Customer addresses, phone numbers, emails redacted from audit trail unless critical for ticket
- **Identity Preservation:** Customer and vendor names appear in audit trail only for business necessity; no unnecessary PII exposure

### Agent Constraints
- **Vendor Communications:** Agents never email vendors or compose outbound mail; all work internal to board
- **Customer Communications:** Agents draft responses for human review; never send directly to customers
- **Payment Authority:** Agents present options and prepare memos; humans make all approval decisions
- **Database Writes:** Restricted to `log_payment()` and audit trail append only

---

## Running the Server

```bash
cd mcp_server
python server.py
```

The server is stateless and queries the database on-demand for each request.

---

## Error Handling
- All tools return JSON with error field on failure
- Database connection errors are surfaced to agents for graceful handling
- Agents should check `"found": false` or `"success": false` before proceeding

---

## Design Principles
1. **Single Source of Truth:** All shop data comes from `campus_customs_new.db`; no secondary layers or hallucinated data
2. **Full Agent Connectivity:** Any agent can call any tool; Boss does not gate access
3. **Human-in-Loop Payments:** Accounting prepares, humans approve, tools execute
4. **Audit Everything:** Each operation logged with agent, action, input, output, status
