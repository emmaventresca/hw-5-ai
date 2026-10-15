"""
The Campus Customs agent team, built with Pydantic AI.

Five agents — Boss, Inventory, Accounting, Facilities, Customer Service — each
running on gpt-6-luna. Every agent can delegate to every other agent, and every
fact any of them states comes from an MCP tools/call against
mcp_server/server.py. There is no second data layer: the tools registered
below are thin pass-throughs to the MCP client, nothing more.

Agents propose. They never move money. A proposed payment is re-checked against
the database before it is offered to a human, so a hallucinated amount cannot
reach the cash path.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal, Optional

from dotenv import load_dotenv
from pydantic import BaseModel, Field

from backend.mcp_client import ToolRecorder, mcp

PROJECT_ROOT = Path(__file__).parent.parent
PROMPTS_DIR = Path(__file__).parent / "prompts"

load_dotenv(dotenv_path=PROJECT_ROOT / ".env")

MODEL_NAME = os.getenv("OPENAI_MODEL", "gpt-6-luna")
MAX_DELEGATION_DEPTH = 3   # chain length, cycles blocked separately

AGENT_FILES = {
    "Boss": "boss.md",
    "Inventory": "inventory.md",
    "Accounting": "accounting.md",
    "Facilities": "facilities.md",
    "Customer Service": "customer_service.md",
}

TEAM_NOTE = """

## Working with the rest of the team

You are one of five agents: Boss, Inventory, Accounting, Facilities and
Customer Service. Any of you can ask any other for help with `ask_teammate`.

Rules you do not break:

- Call `get_desk_today` before you say anything is overdue or due soon. Do
  not assume what today's date is.
- Never state a number you have not read from a tool. If you need stock, a
  price, a balance, an invoice or a lease, call the tool. Do not estimate.
- You cannot move money. Accounting prepares a payment and a human releases it.
- Nothing is sent to a customer or a vendor. Drafts stay on the board.
- Keep your answer to a few sentences. Say what you found, the numbers you
  read, and what should happen next.
"""


BOSS_NOTE = """

## Your order of work, every single time

1. Call `get_tickets` first. You read the board before you do anything else, so
   you know what the ticket actually says rather than trusting the summary you
   were handed.
2. Decide who the work belongs to, then delegate with `ask_teammate`. You are
   the one who routes. Do not do a specialist's job yourself when that
   specialist exists — send a stock question to Inventory, money to Accounting,
   the shop space to Facilities, and anything the customer will read to
   Customer Service.
3. Pull their answers together and return the resolution.

You will be refused if you try to delegate before reading the board.
"""


class AgentUnavailable(RuntimeError):
    """Raised when the model cannot be reached, so callers can fall back."""


class TicketResolution(BaseModel):
    """What the Boss hands back once the team has worked a ticket."""

    summary: str = Field(description="Two or three sentences on what the team decided.")
    needs_payment: bool = Field(description="True only if money must leave the account.")
    payment_kind: Optional[Literal["vendor_payment", "rent_payment"]] = None
    payment_ref_id: Optional[int] = Field(
        default=None, description="Invoice id for a vendor payment, lease id for rent.")
    payment_amount: Optional[float] = Field(
        default=None, description="Amount read from the database, never estimated.")
    payee: Optional[str] = None
    reason: Optional[str] = Field(
        default=None, description="One sentence a human can approve or decline on.")


# ---------------------------------------------------------------------------
# MCP tools. Each one is a pass-through to the MCP server; no logic lives here.
# ---------------------------------------------------------------------------

def _register_mcp_tools(agent, rec: ToolRecorder, agent_name: str, state: dict):
    @agent.tool_plain
    def get_desk_today() -> dict:
        """The shop's current date. Call this before judging whether anything is
        overdue — never assume today's date."""
        return rec.call("get_desk_today")

    @agent.tool_plain
    def get_tickets() -> dict:
        """Every open ticket on the board, with its linked invoice or lease."""
        result = rec.call("get_tickets")
        if agent_name == "Boss":
            # The Boss reads the board before it is allowed to delegate.
            state["board_read"] = True
        return result

    @agent.tool_plain
    def get_inventory_stock(sku: str, size: str) -> dict:
        """On-hand quantity, product name and aisle for one SKU in one size."""
        return rec.call("get_inventory_stock", sku=sku, size=size)

    @agent.tool_plain
    def get_vendors() -> dict:
        """All vendors with their specialty and lead time in days."""
        return rec.call("get_vendors")

    @agent.tool_plain
    def get_open_invoices_for_vendor(vendor_id: int) -> dict:
        """Unpaid invoices for a vendor. They will not ship while one is open."""
        return rec.call("get_open_invoices_for_vendor", vendor_id=vendor_id)

    @agent.tool_plain
    def get_cash_balance() -> dict:
        """Current checking balance. Read this before proposing any payment."""
        return rec.call("get_cash_balance")

    @agent.tool_plain
    def get_lease_details(lease_id: int) -> dict:
        """One lease: space, landlord, monthly rent and next due date."""
        return rec.call("get_lease_details", lease_id=lease_id)

    @agent.tool_plain
    def get_all_leases() -> dict:
        """The full lease portfolio, to spot rents falling due together."""
        return rec.call("get_all_leases")

    @agent.tool_plain
    def get_pricing(sku: str) -> dict:
        """Unit cost, list price and true margin for a SKU. margin_percent is
        measured against list price; markup_percent is against cost."""
        return rec.call("get_pricing", sku=sku)


def _load_prompt(agent_name: str) -> str:
    path = PROMPTS_DIR / AGENT_FILES[agent_name]
    return path.read_text(encoding="utf-8") + TEAM_NOTE


def build_team(rec: ToolRecorder, on_delegate=None):
    """
    Build all five agents and wire every one to every other.

    `on_delegate(caller, callee, question, answer, tools_used)` is called after
    each delegation so the orchestrator can write it to the audit trail.
    """
    from pydantic_ai import Agent
    from pydantic_ai.models.openai import OpenAIChatModel, OpenAIChatModelSettings

    model = OpenAIChatModel(MODEL_NAME)
    # gpt-6-luna rejects function tools unless reasoning is switched off.
    settings = OpenAIChatModelSettings(openai_reasoning_effort="none")

    agents: dict = {}
    chain: list = []          # agents currently mid-delegation, for cycle detection
    state = {"board_read": False}

    for name in AGENT_FILES:
        prompt = _load_prompt(name)
        if name == "Boss":
            prompt += BOSS_NOTE
        agent = Agent(
            model,
            model_settings=settings,
            system_prompt=prompt,
            output_type=TicketResolution if name == "Boss" else str,
            retries=2,
        )
        _register_mcp_tools(agent, rec, name, state)
        agents[name] = agent

    teammates = ", ".join(AGENT_FILES)

    def _make_delegate(caller: str):
        # Must be async: tools run inside the agent's event loop, so a nested
        # run_sync() would raise. await target.run(...) is the supported path.
        async def ask_teammate(agent_name: str, question: str) -> str:
            target = agents.get(agent_name)
            if target is None:
                return (f"There is no agent called {agent_name!r}. "
                        f"Pick one of: {teammates}.")
            if agent_name == caller:
                return "You cannot delegate to yourself. Answer it or ask someone else."
            if caller == "Boss" and not state["board_read"]:
                return ("You have not read the board yet. Call get_tickets first so you "
                        "know what this ticket actually says, then delegate.")
            if agent_name in chain:
                # Without this, Inventory asks Accounting, Accounting asks Inventory
                # back, and the pair burns the token budget agreeing with each other.
                return (f"{agent_name} is already working on this ticket further up the "
                        f"chain. Use what they told you rather than asking again.")
            if len(chain) >= MAX_DELEGATION_DEPTH:
                return ("Delegation limit reached. Answer with what the team already "
                        "established rather than handing off again.")

            chain.append(agent_name)
            try:
                with rec.scope() as used:
                    result = await target.run(question)
                    reply = result.output
                    if isinstance(reply, TicketResolution):
                        # The Boss answers in a structured form; a teammate wants prose.
                        reply = reply.summary
            except Exception as exc:
                return f"{agent_name} could not be reached: {exc}"
            finally:
                chain.remove(agent_name)

            if on_delegate:
                on_delegate(caller, agent_name, question, str(reply), used)
            return str(reply)

        ask_teammate.__doc__ = (
            f"Ask another agent on the team for help. agent_name must be one of: "
            f"{teammates}. Use this whenever the answer belongs to their area."
        )
        return ask_teammate

    for name, agent in agents.items():
        agent.tool_plain(_make_delegate(name))

    return agents


def llm_available() -> bool:
    """True when a key is configured and the pydantic-ai stack imports."""
    if not (os.getenv("OPENAI_API_KEY") or "").strip():
        return False
    try:
        import pydantic_ai  # noqa: F401
        from pydantic_ai.models.openai import OpenAIChatModel  # noqa: F401
    except Exception:
        return False
    return True
