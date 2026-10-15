import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import './App.css'

const API = 'http://localhost:8000'

type Ticket = {
  id: number
  type: string
  requester: string
  subject: string
  sku: string | null
  size: string | null
  qty: number | null
  status: string
  created_at: string
}

type Draft = { to: string; subject: string; body: string }
type MathRow = { label: string; value: string; total?: boolean }

type AgentEvent = {
  timestamp: string
  agent: string
  action: string
  ticket_id: number | null
  tools_used: string[]
  output: string
  status: string
  draft?: Draft | null
  math?: MathRow[] | null
  delegated_by?: string | null
  engine?: string | null
}

type Pending = {
  kind: string
  ref_id: number
  amount: number
  ticket_id: number
  payee: string
  reason: string
  balance_after: number
}

type Balance = { account: string; balance: number; date: string }

const ROSTER = [
  { name: 'Boss', animal: '🐰', beat: 'Reads every ticket, decides who works it' },
  { name: 'Inventory', animal: '🐢', beat: 'Stock counts, vendors, lead times' },
  { name: 'Accounting', animal: '🦜', beat: 'Cash, invoices, margins' },
  { name: 'Facilities', animal: '🐭', beat: 'Leases, rent, the shop space' },
  { name: 'Customer Service', animal: '🐱', beat: 'Drafts what the customer reads' },
]

const TAGLINES = [
  'Small shop, sharp team.',
  'Read it, route it, close it.',
  'Nothing ships until the numbers agree.',
  'Every dollar out gets a human behind it.',
  'Good records beat good memory.',
]

const TYPE_LABEL: Record<string, string> = {
  customer_order: 'Customer order',
  rent_notice: 'Rent notice',
  price_override: 'Price override',
}

const money = (n: number) =>
  n.toLocaleString('en-US', { style: 'currency', currency: 'USD', minimumFractionDigits: 2 })

const shortDate = (iso: string) =>
  new Date(iso).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })

const clock = (iso: string) =>
  new Date(iso).toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' })

export default function App() {
  const [tickets, setTickets] = useState<Ticket[]>([])
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [balance, setBalance] = useState<Balance | null>(null)
  const [events, setEvents] = useState<AgentEvent[]>([])
  const [revealed, setRevealed] = useState(0)
  const [pending, setPending] = useState<Pending | null>(null)
  const [runningId, setRunningId] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [flash, setFlash] = useState(false)
  const [approving, setApproving] = useState(false)
  const [loading, setLoading] = useState(true)
  const [openSheets, setOpenSheets] = useState<Record<number, boolean>>({})

  const toggleSheet = (i: number) =>
    setOpenSheets((prev) => ({ ...prev, [i]: !prev[i] }))

  const tagline = useRef(TAGLINES[Math.floor(Math.random() * TAGLINES.length)]).current

  const load = useCallback(async () => {
    try {
      const [t, b] = await Promise.all([
        fetch(`${API}/tickets`).then((r) => r.json()),
        fetch(`${API}/cash-balance`).then((r) => r.json()),
      ])
      setTickets(t)
      setBalance(b)
      setError(null)
    } catch {
      setError('Cannot reach the backend on localhost:8000. Start it with: uvicorn backend.main:app --reload --port 8000')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    load()
  }, [load])

  // Reveal the run one step at a time so the handoffs are legible. The content
  // is exactly what the backend returned; only the pacing is client-side.
  useEffect(() => {
    if (revealed >= events.length) return
    const id = setTimeout(() => setRevealed((n) => n + 1), revealed === 0 ? 200 : 700)
    return () => clearTimeout(id)
  }, [revealed, events])

  const selected = tickets.find((t) => t.id === selectedId) ?? null
  const shown = events.slice(0, revealed)
  const settling = revealed < events.length
  const nextAgent = settling ? events[revealed].agent : null

  const selectTicket = (id: number) => {
    if (runningId) return
    setSelectedId(id)
    setEvents([])
    setRevealed(0)
    setPending(null)
    setError(null)
    setOpenSheets({})
  }

  const runTicket = async (id: number) => {
    setRunningId(id)
    setEvents([])
    setRevealed(0)
    setPending(null)
    setError(null)
    setOpenSheets({})
    try {
      const res = await fetch(`${API}/run-ticket/${id}`, { method: 'POST' })
      if (!res.ok) throw new Error(await res.text())
      const data = await res.json()
      setEvents(data.events ?? [])
      setPending(data.pending_approval ?? null)
      await load()
    } catch {
      setError(`Ticket ${id} did not run. Check that the backend is up.`)
    } finally {
      setRunningId(null)
    }
  }

  const approve = async () => {
    if (!pending) return
    setApproving(true)
    try {
      const res = await fetch(`${API}/approve-payment`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          kind: pending.kind,
          ref_id: pending.ref_id,
          amount: pending.amount,
          approved_by: 'Desk operator',
          ticket_id: pending.ticket_id,
        }),
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail ?? 'refused')
      setEvents((prev) => [
        ...prev,
        {
          timestamp: new Date().toISOString(),
          agent: 'Accounting',
          action: 'Record payment',
          ticket_id: pending.ticket_id,
          tools_used: ['log_payment'],
          output: `Paid ${money(data.amount)} from checking. Balance ${money(data.previous_balance)} to ${money(data.new_balance)}.`,
          status: 'complete',
        },
      ])
      setRevealed((n) => n + 1)
      setPending(null)
      setFlash(true)
      setTimeout(() => setFlash(false), 1200)
      await load()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Payment refused.')
    } finally {
      setApproving(false)
    }
  }

  const resetBoard = async () => {
    await fetch(`${API}/reset-db`, { method: 'POST' })
    setEvents([])
    setRevealed(0)
    setPending(null)
    setSelectedId(null)
    setError(null)
    await load()
  }

  const agentState = (name: string) => {
    if (!events.length) return runningId ? 'queued' : 'idle'
    if (name === nextAgent) return 'working'
    if (shown.some((e) => e.agent === name)) return 'done'
    if (events.some((e) => e.agent === name)) return 'queued'
    return 'off'
  }

  const summary = useMemo(() => {
    const byAgent = new Map<string, AgentEvent[]>()
    for (const e of shown) {
      if (e.agent === 'Human') continue
      byAgent.set(e.agent, [...(byAgent.get(e.agent) ?? []), e])
    }
    return [...byAgent.entries()]
  }, [shown])

  const openCount = tickets.filter((t) => t.status === 'open').length

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <span className="brand-mark" aria-hidden="true">🐶</span>
          <span className="brand-text">
            <span className="brand-name">Campus Customs</span>
            <span className="brand-sub">Operations desk</span>
          </span>
        </div>
        <p className="tagline">{tagline}</p>
        <div className="topbar-meta">
          <div className="meta">
            <span className="meta-label">Shop date</span>
            <span className="meta-value">{balance?.date ?? '—'}</span>
          </div>
          <div className="meta">
            <span className="meta-label">Open</span>
            <span className="meta-value">{openCount} of {tickets.length}</span>
          </div>
          <div className={`meta meta-cash${flash ? ' is-flash' : ''}`}>
            <span className="meta-label">Checking</span>
            <span className="meta-value">{balance ? money(balance.balance) : '—'}</span>
          </div>
          <button className="btn btn-ghost" onClick={resetBoard}>Reset board</button>
        </div>
      </header>

      {error && <div className="banner" role="alert">{error}</div>}

      <div className="grid">
        <aside className="panel rail">
          <h2 className="panel-title">The team</h2>
          <ul className="roster">
            {ROSTER.map((a) => {
              const state = agentState(a.name)
              const last = [...shown].reverse().find((e) => e.agent === a.name)
              return (
                <li key={a.name} className={`agent is-${state}`}>
                  <span className="agent-animal" aria-hidden="true">{a.animal}</span>
                  <span className="agent-body">
                    <span className="agent-top">
                      <span className="agent-name">{a.name}</span>
                      <span className={`dot is-${state}`} />
                    </span>
                    <span className="agent-beat">{last ? last.action : a.beat}</span>
                  </span>
                </li>
              )
            })}
          </ul>
          <p className="rail-note">
            Agents stay dim until a ticket actually routes to them.
          </p>
        </aside>

        <main className="panel main">
          <div className="panel-head">
            <h2 className="panel-title">Tickets</h2>
            <span className="panel-hint">Pick a row to open it</span>
          </div>

          {loading ? (
            <p className="empty">Loading the board…</p>
          ) : tickets.length === 0 ? (
            <p className="empty">No tickets on the board.</p>
          ) : (
            <table className="table">
              <thead>
                <tr>
                  <th className="col-id">Ticket</th>
                  <th className="col-type">Type</th>
                  <th>Subject</th>
                  <th>Requester</th>
                  <th className="col-item">Item</th>
                  <th className="col-num">Qty</th>
                  <th className="col-opened">Opened</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {tickets.map((t) => (
                  <tr
                    key={t.id}
                    className={t.id === selectedId ? 'is-selected' : ''}
                    onClick={() => selectTicket(t.id)}
                  >
                    <td className="col-id">{t.id}</td>
                    <td className="col-type muted">{TYPE_LABEL[t.type] ?? t.type}</td>
                    <td className="strong">{t.subject}</td>
                    <td className="muted">{t.requester}</td>
                    <td className="col-item mono">{t.sku ? `${t.sku} · ${t.size}` : '—'}</td>
                    <td className="col-num mono">{t.qty ?? '—'}</td>
                    <td className="col-opened muted">{shortDate(t.created_at)}</td>
                    <td><span className={`pill is-${t.status}`}>{t.status}</span></td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}

          {selected && (
            <section className="detail">
              <div className="detail-head">
                <div>
                  <h3 className="detail-title">
                    <span className="detail-id">#{selected.id}</span> {selected.subject}
                  </h3>
                  <p className="detail-sub">
                    {TYPE_LABEL[selected.type] ?? selected.type} · {selected.requester} · opened {shortDate(selected.created_at)}
                  </p>
                </div>
                <button
                  className="btn btn-primary"
                  disabled={runningId !== null || selected.status === 'resolved'}
                  onClick={() => runTicket(selected.id)}
                >
                  {runningId === selected.id
                    ? 'Running…'
                    : selected.status === 'resolved'
                      ? 'Resolved'
                      : 'Run agent team'}
                </button>
              </div>

              <dl className="facts">
                <div><dt>SKU</dt><dd className="mono">{selected.sku ?? '—'}</dd></div>
                <div><dt>Size</dt><dd className="mono">{selected.size ?? '—'}</dd></div>
                <div><dt>Qty</dt><dd className="mono">{selected.qty ?? '—'}</dd></div>
                <div><dt>Status</dt><dd><span className={`pill is-${selected.status}`}>{selected.status}</span></dd></div>
              </dl>

              {summary.length > 0 && (
                <div className="summary">
                  <h4 className="summary-title">What each agent did</h4>
                  <ul>
                    {summary.map(([agent, list]) => (
                      <li key={agent}>
                        <span className="summary-agent">
                          {ROSTER.find((r) => r.name === agent)?.animal} {agent}
                        </span>
                        <span className="summary-actions">
                          {list.map((e) => e.action).join(' · ')}
                        </span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </section>
          )}
        </main>

        <aside className="panel feed">
          <div className="panel-head">
            <h2 className="panel-title">Activity</h2>
            {settling && <span className="live">live</span>}
          </div>

          {shown.length === 0 ? (
            <p className="empty">
              {selected
                ? 'Nothing yet. Run the agent team to see the handoffs.'
                : 'Pick a ticket to get started.'}
            </p>
          ) : (
            <ol className="log">
              {shown.map((e, i) => (
                <li key={i} className={`log-item is-${e.status}`}>
                  <div className="log-head">
                    <span className="log-agent">
                      <span aria-hidden="true">{ROSTER.find((r) => r.name === e.agent)?.animal ?? '👤'}</span>
                      {e.agent}
                    </span>
                    <span className="log-time">{clock(e.timestamp)}</span>
                  </div>
                  <p className="log-action">
                    {e.action}
                    {e.delegated_by && (
                      <span className="log-from">asked by {e.delegated_by}</span>
                    )}
                  </p>
                  <p className="log-output">{e.output}</p>
                  {e.tools_used.length > 0 && (
                    <p className="log-tools">
                      {e.tools_used.map((t) => <code key={t}>{t}</code>)}
                    </p>
                  )}

                  {(e.draft || e.math) && (
                    <button
                      className={`reveal${openSheets[i] ? ' is-open' : ''}`}
                      aria-expanded={!!openSheets[i]}
                      onClick={() => toggleSheet(i)}
                    >
                      {e.draft
                        ? openSheets[i] ? 'Hide email draft' : 'Show email draft'
                        : openSheets[i] ? 'Hide the math' : 'Show the math'}
                    </button>
                  )}

                  {openSheets[i] && e.draft && (
                    <div className="sheet">
                      <div className="sheet-head">
                        <dl className="sheet-row"><dt>To</dt><dd>{e.draft.to}</dd></dl>
                        <dl className="sheet-row"><dt>Subject</dt><dd>{e.draft.subject}</dd></dl>
                      </div>
                      <p className="sheet-body">{e.draft.body}</p>
                      <p className="sheet-foot">Draft only. Nothing is sent from this board.</p>
                    </div>
                  )}

                  {openSheets[i] && e.math && (
                    <div className="sheet">
                      <dl className="math">
                        {e.math.map((row) => (
                          <div key={row.label} className={`math-row${row.total ? ' is-total' : ''}`}>
                            <dt>{row.label}</dt>
                            <dd>{row.value}</dd>
                          </div>
                        ))}
                      </dl>
                    </div>
                  )}
                </li>
              ))}
            </ol>
          )}

          {pending && !settling && (
            <div className="approval">
              <p className="approval-label">Needs your approval</p>
              <p className="approval-amount">{money(pending.amount)}</p>
              <p className="approval-payee">to {pending.payee}</p>
              <p className="approval-reason">{pending.reason}</p>
              <dl className="approval-facts">
                <div><dt>Reference</dt><dd className="mono">{pending.kind === 'rent_payment' ? 'Lease' : 'Invoice'} {pending.ref_id}</dd></div>
                <div><dt>Balance after</dt><dd className="mono">{money(pending.balance_after)}</dd></div>
              </dl>
              <button className="btn btn-approve" onClick={approve} disabled={approving}>
                {approving ? 'Paying…' : 'Approve payment'}
              </button>
              <p className="approval-note">Agents prepared this. Only you can release the cash.</p>
            </div>
          )}
        </aside>
      </div>
    </div>
  )
}
