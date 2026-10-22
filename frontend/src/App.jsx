import { useEffect, useState } from 'react';
import {
  Activity, ArrowDown, Check, CircleAlert, FileText, Inbox, Landmark,
  LoaderCircle, Moon, Plus, RefreshCw, Search, ShieldCheck, Sparkles, Sun,
} from 'lucide-react';
import './styles.css';
import './invoice-form.css';

const API = import.meta.env.VITE_API_URL || 'http://localhost:8000';
const PAGES = [
  { id: 'home', label: 'Task home', icon: Sparkles },
  { id: 'inbox', label: 'Company inbox', icon: Inbox },
  { id: 'accounting', label: 'Accounting', icon: Landmark },
  { id: 'activity', label: 'Activity log', icon: Activity },
];
const money = (amount, currency = 'INR') => {
  try {
    return new Intl.NumberFormat('en-IN', { style: 'currency', currency, maximumFractionDigits: 0 }).format(amount);
  } catch {
    return `${Number(amount).toLocaleString('en-IN')} ${currency}`; // codes Intl does not know (e.g. crypto)
  }
};
const inrNote = (invoice) => (invoice?.currency && invoice.currency !== 'INR' && invoice.amount_inr != null
  ? ` ≈ ${money(invoice.amount_inr)}` : '');

const pad = (n) => String(n).padStart(2, '0');
const toLocalInput = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
const toDateInput = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
function oneMonthLater(d) {
  const target = new Date(d.getFullYear(), d.getMonth() + 1, 1);
  const lastDay = new Date(target.getFullYear(), target.getMonth() + 1, 0).getDate();
  target.setDate(Math.min(d.getDate(), lastDay));
  return target;
}
function blankInvoiceForm() {
  const now = new Date();
  return {
    invoice_number: '', vendor: '', amount: '', currency: 'INR',
    received_at: toLocalInput(now), due_date: toDateInput(oneMonthLater(now)),
    id: '', sender: '', subject: '',
  };
}

async function request(path, options = {}) {
  const headers = { ...(options.headers || {}) };
  const key = sessionStorage.getItem('demoKey');
  if (key) headers['X-Demo-Key'] = key;
  const response = await fetch(`${API}${path}`, { ...options, headers });
  if (response.status === 401) {
    sessionStorage.removeItem('demoKey'); // the stored key (if any) was wrong
    const entered = window.prompt('Enter the demo key');
    if (entered) {
      sessionStorage.setItem('demoKey', entered);
      return request(path, options);
    }
  }
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = Array.isArray(body.detail)
      ? body.detail.map((d) => `${(d.loc || []).slice(1).join('.')}: ${d.msg}`).join('; ')
      : body.detail;
    throw new Error(detail || 'Request failed');
  }
  return body;
}

function App() {
  const [page, setPage] = useState('home');
  const [theme, setTheme] = useState(() => { try { return localStorage.getItem('theme') || 'dark'; } catch { return 'dark'; } });
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    try { localStorage.setItem('theme', theme); } catch { /* storage unavailable */ }
  }, [theme]);
  const [messages, setMessages] = useState([]);
  const [records, setRecords] = useState([]);
  const [selected, setSelected] = useState(null);
  const [query, setQuery] = useState('Acme');
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');
  const [apiReady, setApiReady] = useState(false);
  const [taskText, setTaskText] = useState('Find the latest invoice from Acme Corp and process it.');
  const [agentResult, setAgentResult] = useState(null);
  const [showCreate, setShowCreate] = useState(false);
  const [form, setForm] = useState(blankInvoiceForm);
  const [currencies, setCurrencies] = useState([]);
  const [rate, setRate] = useState(null);
  const currencyCode = form.currency.trim().toUpperCase();

  useEffect(() => { request('/api/currencies').then(setCurrencies).catch(() => {}); }, []);
  useEffect(() => {
    if (!showCreate || !currencyCode || currencyCode === 'INR') return undefined;
    let cancelled = false;
    const timer = setTimeout(() => {
      request(`/api/rates/${encodeURIComponent(currencyCode)}`)
        .then((r) => { if (!cancelled) setRate({ ...r, input: currencyCode }); })
        .catch((e) => { if (!cancelled) setRate({ input: currencyCode, error: e.message }); });
    }, 400);
    return () => { cancelled = true; clearTimeout(timer); };
  }, [currencyCode, showCreate]);

  async function refresh() {
    try {
      const [inbox, accounting] = await Promise.all([
        request(`/api/inbox/messages?query=${encodeURIComponent(query)}`),
        request('/api/accounting/invoices'),
      ]);
      setMessages(inbox);
      setRecords(accounting);
      setApiReady(true);
      setError('');
      if (selected) setSelected(inbox.find((item) => item.id === selected.id) || selected);
    } catch (e) {
      setApiReady(false);
      setError(e.message);
    }
  }

  useEffect(() => { refresh(); }, []);
  useEffect(() => {
    if (page === 'inbox' || page === 'accounting') refresh();
  }, [page]);

  async function search() {
    setBusy(true); setError('');
    try {
      setMessages(await request(`/api/inbox/messages?query=${encodeURIComponent(query)}`));
      setNotice('Inbox refreshed');
    } catch (e) { setError(e.message); }
    finally { setBusy(false); }
  }

  async function openMessage(message) {
    setBusy(true); setError(''); setNotice('');
    try { setSelected(await request(`/api/inbox/messages/${message.id}`)); }
    catch (e) { setError(e.message); }
    finally { setBusy(false); }
  }

  const setField = (key) => (e) => setForm((current) => ({ ...current, [key]: e.target.value }));

  async function createInvoice(event) {
    event.preventDefault();
    setBusy(true); setError(''); setNotice('');
    try {
      const payload = {
        invoice_number: form.invoice_number.trim(),
        vendor: form.vendor.trim(),
        amount: form.amount === '' ? 0 : Number(form.amount),
        currency: form.currency.trim() || 'INR',
        received_at: form.received_at || null,
        due_date: form.due_date || null,
      };
      ['id', 'sender', 'subject'].forEach((key) => { if (form[key].trim()) payload[key] = form[key].trim(); });
      const created = await request('/api/inbox/messages', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      setQuery('');
      setMessages(await request('/api/inbox/messages'));
      setSelected(created);
      setForm(blankInvoiceForm());
      setShowCreate(false);
      setNotice(`Invoice ${created.invoice_number} saved to the inbox as ${money(created.amount, created.currency)}${inrNote(created)}.`);
    } catch (e) { setError(e.message); }
    finally { setBusy(false); }
  }

  async function processInvoice() {
    if (!selected) return;
    setBusy(true); setNotice(''); setError('');
    try {
      const result = await request('/api/accounting/invoices', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ invoice_number: selected.invoice_number, vendor: selected.vendor, amount: selected.amount, currency: selected.currency || 'INR', due_date: selected.due_date }),
      });
      const verified = await request(`/api/accounting/invoices/${encodeURIComponent(selected.invoice_number)}`);
      setRecords((current) => [verified, ...current.filter((r) => r.invoice_number !== verified.invoice_number)]);
      setNotice(`Submitted and independently checked: ${result.invoice_number} is ${verified.status}.`);
    } catch (e) {
      if (e.message.includes('already been processed')) {
        try {
          const verified = await request(`/api/accounting/invoices/${encodeURIComponent(selected.invoice_number)}`);
          setNotice(`Already processed. Accounting confirms ${verified.invoice_number} is ${verified.status}.`);
          setRecords((current) => [verified, ...current.filter((r) => r.invoice_number !== verified.invoice_number)]);
        } catch (verifyError) { setError(verifyError.message); }
      } else setError(e.message);
    } finally { setBusy(false); }
  }

  async function runAgentTask() {
    setBusy(true); setError(''); setNotice(''); setAgentResult(null);
    try {
      setAgentResult(await request('/api/tasks', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ task: taskText }),
      }));
    } catch (e) { setError(e.message); }
    finally { setBusy(false); }
  }

  async function answerApproval(approved) {
    if (!agentResult?.task_id) return;
    setBusy(true); setError('');
    try {
      setAgentResult(await request(`/api/tasks/${agentResult.task_id}/approval`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ approved }),
      }));
      await refresh();
    } catch (e) { setError(e.message); }
    finally { setBusy(false); }
  }

  const selectedPage = PAGES.find((item) => item.id === page) || PAGES[0];
  const alreadyProcessed = selected && records.some((record) => record.invoice_number === selected.invoice_number);
  const latestAcme = messages.find((message) => message.sender.toLowerCase().includes('acme'));
  const agentStatus = agentResult?.approval_status === 'pending' ? 'Needs approval'
    : agentResult?.completed ? 'Completed'
      : agentResult?.failed ? 'Stopped'
        : busy ? 'Working' : 'Ready';

  return <div className="app-shell">
    <aside className="sidebar">
      <button className="brand" onClick={() => setPage('home')} aria-label="OpsPilot home">
        <span className="brand-mark"><Sparkles size={18} /></span>
        <span className="brand-copy"><strong>OpsPilot</strong><small>AI task worker</small></span>
      </button>
      <p className="workspace-label">WORKSPACE</p>
      <nav className="side-nav" aria-label="Main navigation">
        {PAGES.map(({ id, label, icon: Icon }) => <button key={id} className={`nav-item ${page === id ? 'active' : ''}`} onClick={() => { setPage(id); setError(''); setNotice(''); }} aria-current={page === id ? 'page' : undefined}>
          <Icon size={18} /><span>{label}</span>{page === id && <span className="nav-dot" />}
        </button>)}
      </nav>
      <div className="sidebar-bottom"><div className="environment"><span className={`online-dot ${apiReady ? '' : 'offline-dot'}`} /><div><b>Local environment</b><small>{apiReady ? 'API connected' : 'API offline'}</small></div></div></div>
    </aside>

    <main className="main-content">
      <header className="topbar">
        <div className="mobile-brand"><span className="brand-mark"><Sparkles size={17} /></span><strong>OpsPilot</strong></div>
        <div className="breadcrumbs"><span>Workspace</span><span className="crumb-separator">/</span><b>{selectedPage.label}</b></div>
        <div className="top-actions">
          <button className="icon-button theme-toggle" aria-label={`Switch to ${theme === 'dark' ? 'light' : 'dark'} theme`} onClick={() => setTheme((t) => (t === 'dark' ? 'light' : 'dark'))}>{theme === 'dark' ? <Sun size={16} /> : <Moon size={16} />}</button>
          {page !== 'home' && <button className="icon-button refresh-button" aria-label="Refresh page data" onClick={refresh}><RefreshCw size={16} /><span>Refresh</span></button>}
          <div className={`connection ${apiReady ? '' : 'offline'}`}><span />{apiReady ? 'Connected' : 'Offline'}</div>
        </div>
      </header>

      <div className={`page-content page-${page}`}>
        {!apiReady && <div className="banner error-banner"><CircleAlert size={18} /><div><b>Backend not connected</b><span>Waking up the server, this can take up to a minute. Thanks for your patience!</span></div></div>}
        {notice && <div className="banner success-banner"><Check size={17} /><span>{notice}</span><button onClick={() => setNotice('')} aria-label="Dismiss message">×</button></div>}
        {error && apiReady && <div className="banner error-banner"><CircleAlert size={17} /><span>{error}</span><button onClick={() => setError('')} aria-label="Dismiss error">×</button></div>}

        {page === 'home' && <>
          <section className="home-intro"><h1>What should I take care of?</h1></section>
          <section className="task-card">
            <div className="task-card-heading"><div className="task-icon"><Sparkles size={18} /></div><div><h2>New task</h2></div><span className={`status-pill ${agentResult?.approval_status === 'pending' ? 'waiting' : agentResult?.completed ? 'complete' : agentResult?.failed ? 'failed' : ''}`}><span />{agentStatus}</span></div>
            <label htmlFor="task">TASK DESCRIPTION</label>
            <textarea id="task" value={taskText} onChange={(e) => setTaskText(e.target.value)} placeholder="For example: Process the latest Acme invoice" rows={2} />
            <div className="task-controls"><div className="task-hint"><ShieldCheck size={15} /><span>High-value invoices pause for your approval.</span></div><button className="button primary run-button" onClick={runAgentTask} disabled={busy || !apiReady || taskText.trim().length < 5}>{busy ? <LoaderCircle className="spin" size={17} /> : <Sparkles size={16} />} {busy ? 'Working…' : 'Run task'}</button></div>
            {agentResult?.approval_status === 'pending' && agentResult.invoice && <div className="approval-card"><div className="approval-title"><ShieldCheck size={19} /><div><b>Approval required</b><span>This invoice is above the ₹50,000 limit.</span></div></div><div className="approval-facts"><span><small>INVOICE</small><b>{agentResult.invoice.invoice_number}</b></span><span><small>VENDOR</small><b>{agentResult.invoice.vendor}</b></span><span><small>AMOUNT</small><b>{money(agentResult.invoice.amount, agentResult.invoice.currency)}{inrNote(agentResult.invoice)}</b></span></div><div className="approval-actions"><button className="button reject" onClick={() => answerApproval(false)} disabled={busy}>Reject</button><button className="button approve" onClick={() => answerApproval(true)} disabled={busy}>Approve and continue</button></div></div>}
            {agentResult?.final_summary && <div className={`agent-result ${agentResult.completed ? 'result-success' : 'result-failure'}`}>{agentResult.completed ? <Check size={17} /> : <CircleAlert size={17} />}<div><b>{agentResult.completed ? 'Task completed and verified' : agentResult.final_summary?.startsWith('No matching invoice') ? 'No matching invoice' : 'Task stopped'}</b><span>{agentResult.final_summary}</span></div></div>}
          </section>
        </>}

        {page === 'inbox' && <>
          <section className="page-heading"><div><h1>Company inbox</h1></div><span className="local-tag"><span /> LOCAL</span></section>
          <article className="panel app-panel" id="inbox">
            <div className="panel-head"><div className="app-title"><div className="app-icon inbox-icon"><Inbox size={19} /></div><div><h2>Inbox messages</h2></div></div><span className="count-tag">{messages.length} messages</span></div>
            <div className="search-bar"><Search size={16} /><input value={query} onChange={(e) => setQuery(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && search()} placeholder="Search sender or subject" aria-label="Search inbox" /><button onClick={search} disabled={busy}>Search</button></div>
            <div className="cf-bar"><button className="button primary" type="button" onClick={() => setShowCreate((v) => !v)}><Plus size={15} /> {showCreate ? 'Close form' : 'Create invoice'}</button></div>
            {showCreate && <form className="cf-form" onSubmit={createInvoice}>
              <div className="cf-grid">
                <label className="cf-field"><span>Invoice number *</span><input value={form.invoice_number} onChange={setField('invoice_number')} placeholder="KBC-5001" required maxLength={40} /></label>
                <label className="cf-field"><span>Vendor *</span><input value={form.vendor} onChange={setField('vendor')} placeholder="KBC Crop" required maxLength={120} /></label>
                <label className="cf-field"><span>Amount <small>(in selected currency, default 0)</small></span><input type="number" min="0" step="1" value={form.amount} onChange={setField('amount')} placeholder="70000" /></label>
                <label className="cf-field"><span>Currency <small>(code, symbol like $ or ¥, or name)</small></span><input list="currency-codes" value={form.currency} onChange={setField('currency')} maxLength={40} placeholder="USD, $, ¥, yen…" /><datalist id="currency-codes">{currencies.map((c) => <option key={c.code} value={c.code}>{c.name}</option>)}</datalist></label>
                <label className="cf-field"><span>Received at</span><input type="datetime-local" value={form.received_at} onChange={setField('received_at')} /></label>
                <label className="cf-field"><span>Due date <small>(default: 1 month later)</small></span><input type="date" value={form.due_date} onChange={setField('due_date')} /></label>
                <label className="cf-field"><span>Sender <small>(default: vendor)</small></span><input value={form.sender} onChange={setField('sender')} placeholder="KBC Crop" /></label>
                <label className="cf-field"><span>Subject <small>(default: Invoice #number)</small></span><input value={form.subject} onChange={setField('subject')} placeholder="Invoice #KBC-5001" /></label>
                <label className="cf-field"><span>Message ID <small>(default: mail-number)</small></span><input value={form.id} onChange={setField('id')} placeholder="mail-kbc-5001" /></label>
              </div>
              {currencyCode && currencyCode !== 'INR' && rate && rate.input === currencyCode && (rate.error || rate.currency !== 'INR') && (
                <p className="cf-rate">{rate.error ? rate.error : `1 ${rate.currency} = ₹${rate.rate.toLocaleString('en-IN', { maximumSignificantDigits: 6 })} (${rate.source === 'live' ? `daily rate, ${rate.date}` : 'offline fallback rate'})${Number(form.amount) > 0 ? ` → about ${money(Math.round(Number(form.amount) * rate.rate))}, used for the ₹50,000 approval rule` : ''}`}</p>
              )}
              <div className="cf-actions"><button type="button" className="button" onClick={() => setForm(blankInvoiceForm())}>Reset</button><button type="submit" className="button primary" disabled={busy || !apiReady}>Save invoice</button></div>
            </form>}
            <div className="message-list">{messages.map((message) => <button className={`message-row ${selected?.id === message.id ? 'selected' : ''}`} key={message.id} onClick={() => openMessage(message)}><span className="sender-avatar">{message.sender[0]}</span><span className="message-info"><span className="message-top"><b>{message.sender}</b><time>{new Date(message.received_at).toLocaleDateString('en-IN', { day: '2-digit', month: 'short' })}</time></span><span className="message-subject">{message.subject}</span></span><ArrowDown className="row-arrow" size={16} /></button>)}{!messages.length && <div className="empty">No matching inbox messages.</div>}</div>
            {selected && <div className="invoice-detail"><div className="detail-heading"><div><span className="detail-label">OPENED INVOICE</span><h3>{selected.invoice_number}</h3></div><span className="invoice-badge"><FileText size={14} /> Invoice</span></div><div className="detail-grid"><div><small>Vendor</small><b>{selected.vendor}</b></div><div><small>Amount</small><b>{money(selected.amount, selected.currency)}{inrNote(selected)}</b></div><div><small>Due date</small><b>{new Date(`${selected.due_date}T00:00:00`).toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' })}</b></div><div><small>Received</small><b>{new Date(selected.received_at).toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' })}</b></div></div><button className="button primary full" onClick={processInvoice} disabled={busy || !apiReady}>{busy ? <LoaderCircle className="spin" size={17} /> : <ArrowDown size={16} />}{alreadyProcessed ? 'Check accounting record' : 'Enter into accounting'}</button></div>}
          </article>
        </>}

        {page === 'accounting' && <>
          <section className="page-heading"><div><h1>Accounting</h1></div><span className="local-tag"><span /> LOCAL</span></section>
          <article className="panel app-panel" id="accounting">
            <div className="panel-head"><div className="app-title"><div className="app-icon accounting-icon"><Landmark size={19} /></div><div><h2>Invoice register</h2></div></div><span className="count-tag">{records.length} processed</span></div>
            <div className="record-head"><span>INVOICE</span><span>AMOUNT</span><span>STATUS</span></div>
            <div className="record-list">{records.map((record) => <div className="record-row" key={record.invoice_number}><div className="record-id"><span className="record-file"><FileText size={16} /></span><span><b>{record.invoice_number}</b><small>{record.vendor}</small></span></div><b className="record-amount">{money(record.amount, record.currency)}{inrNote(record)}</b><span className="processed"><Check size={13} /> {record.status}</span></div>)}{!records.length && <div className="empty ledger-empty"><span className="empty-graphic"><Landmark size={23} /></span><b>No processed invoices yet</b>{latestAcme && <button onClick={() => { setPage('inbox'); openMessage(latestAcme); }}>Open latest Acme invoice <ArrowDown size={14} /></button>}</div>}</div>
            {records.length > 0 && <div className="verification-note"><ShieldCheck size={16} /><span>Records are read back from the accounting API after submission.</span></div>}
          </article>
        </>}

        {page === 'activity' && <>
          <section className="page-heading"><div><h1>Activity log</h1></div></section>
          <section className="trace-panel"><div className="trace-head"><div><div className="trace-icon"><Activity size={17} /></div><div><h2>Execution trace</h2><p>{agentResult?.task}</p></div></div>{agentResult && <span className="human-tag">AGENT TRACE</span>}</div>
            <div className="trace-content">{agentResult?.execution_history?.length ? agentResult.execution_history.map((item, index) => <div className="trace-line" key={`${item.event}-${index}`}><span className={`trace-point ${item.event?.includes('FAIL') || item.event?.includes('REJECT') ? 'trace-failed' : item.event?.includes('SUCCESS') || item.event?.includes('COMPLETED') ? 'done' : 'read'}`} /><div><b>{item.event?.replaceAll('_', ' ')}</b><span>{item.detail}{item.tool ? ` · ${item.tool}` : ''}</span></div><time>{item.time ? new Date(item.time).toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit', second: '2-digit' }) : 'AGENT'}</time></div>) : <div className="empty activity-empty"><span className="empty-graphic"><Activity size={21} /></span><b>No task activity yet</b><button onClick={() => setPage('home')}>Go to task home <ArrowDown size={14} /></button></div>}</div>
            {agentResult?.verification_result && <div className="verification-note"><ShieldCheck size={16} /><span>{agentResult.verification_result.evidence}</span></div>}
          </section>
        </>}

      </div>
    </main>
    <nav className="mobile-nav" aria-label="Mobile navigation">{PAGES.map(({ id, label, icon: Icon }) => <button key={id} onClick={() => { setPage(id); setError(''); setNotice(''); }} className={page === id ? 'active' : ''} aria-current={page === id ? 'page' : undefined}><Icon size={19} /><span>{label === 'Task home' ? 'Home' : label === 'Company inbox' ? 'Inbox' : label === 'Activity log' ? 'Activity' : label}</span></button>)}</nav>
  </div>;
}

export default App;
