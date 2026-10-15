# Design — Campus Customs Operations Desk

The board at `frontend/`, talking to the FastAPI backend on `localhost:8000`.

The brief was a dashboard someone stares at for hours. That one sentence drove
almost every decision below: nothing here is decorative unless it also makes a
long shift easier.

---

## 1. Warm paper instead of white

The canvas is `#f6f3ee`, not `#ffffff`. Pure white at full screen brightness is
the single biggest cause of eye fatigue in all-day tools. The warm off-white
drops the glare without ever reading as "dim," and it gives real white
(`#fffdfa`) somewhere to go — white is now a *signal* that means "this surface
is active," used for the top bar, the selected row, and the activity column.

## 2. Yale navy carries the identity, not a logo

`#10243f` for headings, the wordmark, agent names, and primary buttons. There is
no Yale seal, no crest, no official mark — the identity comes from the colour
itself plus an old-style serif (`Iowan Old Style`, falling back to Georgia) used
*only* for the wordmark, ticket titles, and the approval amount. Three serif
appearances in the whole app. That restraint is what makes it read as collegiate
rather than costume.

## 3. The animals are the team, and they tell the truth

Boss is a rabbit, Inventory a turtle, Accounting a parrot, Facilities a mouse,
Customer Service a lynx. They are genuinely fun to work beside, and they're also
the fastest way to identify who is speaking in the feed — you recognise a shape
faster than you read a word.

The important part: **an agent stays dim until the ticket actually routes to it.**
Run the rent ticket and Inventory and Customer Service stay grey, because rent
never goes near them. An earlier version lit all five on every run; that was a
lie, and a dashboard that lies about who is working is worse than no dashboard.
Each animal sits in a bordered circle and is desaturated while idle, so the
roster reads as a calm column of status rather than a row of stickers.

## 4. One real table, not nine cards

Every ticket field lives in one dense table — ticket, type, subject, requester,
item, qty, opened, status. Rows are 9px-padded and separated by a hairline, not
boxed. You can scan three tickets or thirty with the same eye movement.

The table **sheds columns before it ever scrolls sideways**: `Opened` goes at
1400px, `Type` at 1180px, `Item` at 1040px, and everything dropped is still
visible in the detail panel underneath. Horizontal scroll in a data table is a
bug, not a layout.

## 5. Borders, not shadows

There is exactly one shadow in the entire stylesheet, on the pinned approval
card, because that is the only element that should appear to float above the
page. Everything else is separated by a 1px hairline in a warm grey
(`#e3ddd3`). Radii are 5px. Hairlines at this density stay legible for hours;
stacked shadows and 16px radii turn into visual mush.

## 6. The money action is pinned

The approval card is `position: sticky; bottom: 0` inside the activity column.
The thing that moves real cash is never something you scroll to find. It states
the amount in serif at 27px, who it's going to, *why* the agents prepared it, the
reference row, and — the number that actually matters — the balance you'll be
left with. Then one button.

Its copy is deliberate: *"Agents prepared this. Only you can release the cash."*
That is the whole human-in-the-loop rule in eight words, sitting where the
decision is made.

## 7. The activity feed is a timeline

A 1px rail with a ringed dot per entry, so handoffs read as a sequence rather
than five unrelated cards. Each entry carries the agent, the action in small
caps, the full sentence the backend produced, and the MCP tools it called as
monospace chips. The chips are the audit trail made visible — you can see
`get_lease_details` fire and know the number came from the database.

When one agent delegates to another, the entry carries a small **asked by
Boss** / **asked by Inventory** chip next to the action. That one detail turns
the feed from a list of things that happened into a visible chain of command —
you can see Inventory hit the vendor's unpaid invoice and hand the money
question straight to Accounting.

Entries appear one at a time, about 700ms apart. The content is exactly what
`POST /run-ticket` returned in a single response; only the *pacing* is
client-side, so you can actually watch the team think instead of having five
paragraphs land at once. Nothing is invented to fill the delay — the agents are
real Pydantic AI agents on `gpt-6-luna`, and every figure in those sentences was
fetched through an MCP `tools/call`.

## 8. Numbers behave like numbers

Every figure uses `font-variant-numeric: tabular-nums`, so digits sit in fixed
columns and a balance going from `$3,400.00` to `$2,560.00` doesn't jitter.
SKUs and references are monospace. When the balance changes after an approval it
holds ochre for 1.2 seconds — long enough to catch, short enough to ignore.

## 9. Motion only where it means something

Three animations total: the live dot breathing while a run is in flight, log
entries rising 3px as they land, and the balance flash. No hover lifts, no
floating, no page transitions. In a tool you look at all day, every unnecessary
animation is a small repeated interruption.

## 10. A quiet line of warmth

One short tagline in the top bar, in italic serif, picked at random per load —
*"Nothing ships until the numbers agree."* It's small, grey, and never moves.
A tiny bulldog sits in the wordmark. That's the entire budget for personality
outside the agents, and it's deliberately small: charm that repeats every day
has to be quiet or it becomes irritating.

---

## Palette

| Token | Value | Use |
| --- | --- | --- |
| `--navy` | `#10243f` | Headings, wordmark, primary buttons, timeline dots |
| `--ink` | `#17212e` | Body text |
| `--ink-2` | `#5a6676` | Secondary text, agent outputs |
| `--ink-3` | `#8b94a1` | Labels, metadata, idle states |
| `--paper` | `#f6f3ee` | Canvas |
| `--surface` | `#fffdfa` | Active surfaces |
| `--line` | `#e3ddd3` | Structural hairlines |
| `--accent` | `#a9762f` | Approval card, balance flash |
| Open | `#85590f` on `#fbf0db` | Ticket status |
| Resolved | `#2b6148` on `#e4efe9` | Ticket status |
| Live | `#1a5a84` on `#e5eff7` | Agent working |

Type scale: 10, 11, 12.5, 13, 15, 19, 27. UI in system sans, identity in serif,
data in `ui-monospace`.

---

## What the board does with the backend

| Action | Route |
| --- | --- |
| Load tickets and status | `GET /tickets` |
| Load checking balance and shop date | `GET /cash-balance` |
| Run the agent team on a ticket | `POST /run-ticket/{id}` |
| Release a prepared payment | `POST /approve-payment` |
| Start a clean run | `POST /reset-db` |

Every sentence in the feed is built from values read out of
`data/campus_customs_new.db` — the 0 tees in Aisle B, invoice 501 three days
overdue, $2,400 rent two days out, the 62.1% hoodie margin. The frontend
invents nothing. If the backend is down the board says so and names the command
to start it, rather than quietly falling back to sample data.

Tickets that cost nothing resolve at the end of the run. Tickets that cost money
stay open until a human approves, and only `POST /approve-payment` moves cash.

## Running it

```bash
uvicorn backend.main:app --reload --port 8000
npm --prefix frontend run dev
```
