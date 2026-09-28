const app = document.querySelector('#app');
const toastRegion = document.querySelector('#toast-region');
const state = { token: localStorage.getItem('pulse_token'), user: jsonStorage('pulse_user'), sessions: [], poll: null };

function jsonStorage(key) { try { return JSON.parse(localStorage.getItem(key)); } catch { return null; } }
function esc(value = '') { return String(value).replace(/[&<>'"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'})[c]); }
function icon(name) {
  const icons = {
    calendar: '<svg class="nav-icon" viewBox="0 0 24 24" aria-hidden="true"><rect x="3" y="5" width="18" height="16" rx="2"/><path d="M16 3v4M8 3v4M3 10h18"/></svg>',
    ticket: '<svg class="nav-icon" viewBox="0 0 24 24" aria-hidden="true"><path d="M4 7a2 2 0 0 0 0 4v2a2 2 0 0 0 0 4v1h16v-1a2 2 0 0 0 0-4v-2a2 2 0 0 0 0-4V6H4Z"/><path d="M13 7v10"/></svg>',
    settings: '<svg class="nav-icon" viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .34 1.88l.06.06-2.12 2.12-.06-.06a1.7 1.7 0 0 0-1.88-.34 1.7 1.7 0 0 0-1.04 1.56V20.3h-3v-.08A1.7 1.7 0 0 0 10.66 18.66a1.7 1.7 0 0 0-1.88.34l-.06.06-2.12-2.12.06-.06A1.7 1.7 0 0 0 7 15a1.7 1.7 0 0 0-1.56-1.04H5.3v-3h.14A1.7 1.7 0 0 0 7 9.92a1.7 1.7 0 0 0-.34-1.88L6.6 7.98 8.72 5.86l.06.06a1.7 1.7 0 0 0 1.88.34A1.7 1.7 0 0 0 11.7 4.7v-.08h3v.08a1.7 1.7 0 0 0 1.04 1.56 1.7 1.7 0 0 0 1.88-.34l.06-.06 2.12 2.12-.06.06a1.7 1.7 0 0 0-.34 1.88 1.7 1.7 0 0 0 1.56 1.04h.08v3h-.08A1.7 1.7 0 0 0 19.4 15Z"/></svg>'
  };
  return icons[name];
}
function humanDate(value) { return new Intl.DateTimeFormat('en-GB', { weekday: 'short', day: 'numeric', month: 'short' }).format(new Date(value)); }
function clock(value) { return new Intl.DateTimeFormat('en-GB', { hour: '2-digit', minute: '2-digit', hour12: true }).format(new Date(value)); }
function todayText() { return new Intl.DateTimeFormat('en-GB', { weekday: 'long', day: 'numeric', month: 'long' }).format(new Date()); }
function sessionLabel(s) { return `${humanDate(s.startsAt)} · ${clock(s.startsAt)}`; }
function localInputDate(date = new Date()) { const off = date.getTimezoneOffset() * 60000; return new Date(date - off).toISOString().slice(0, 10); }

function showToast(message, type = '') {
  const toast = document.createElement('div'); toast.className = `toast ${type}`; toast.textContent = message;
  toastRegion.append(toast); setTimeout(() => toast.remove(), 4200);
}
async function api(path, options = {}) {
  const headers = { ...(options.body ? {'Content-Type':'application/json'} : {}), ...(options.headers || {}) };
  if (state.token) headers.Authorization = `Bearer ${state.token}`;
  let res;
  try { res = await fetch(path, { ...options, headers }); } catch { throw { message: 'Unable to reach the server. Check that Pulse is running.' }; }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    if (res.status === 401 && state.token) { signOut(false); }
    throw data.error || { message: 'Something went wrong. Please try again.' };
  }
  return data;
}
function setAuth(token, user) { state.token = token; state.user = user; localStorage.setItem('pulse_token', token); localStorage.setItem('pulse_user', JSON.stringify(user)); }
function signOut(redirect = true) { state.token = null; state.user = null; localStorage.removeItem('pulse_token'); localStorage.removeItem('pulse_user'); if (redirect) location.hash = '#login'; }
function clearPoll() { if (state.poll) clearInterval(state.poll); state.poll = null; }
function activeRoute() { return (location.hash || (state.user ? '#sessions' : '#login')).slice(1).split('?')[0]; }

function authPage(mode) {
  const isLogin = mode === 'login';
  app.innerHTML = `<main class="auth-page">
    <section class="auth-poster" aria-label="Pulse Gym">
      <a class="logo" href="#${isLogin ? 'login' : 'register'}"><i class="logo-mark"></i>pulse</a>
      <div class="poster-copy"><span class="eyebrow">Train on your terms</span><h1>Make room for your strongest self.</h1><p>Book your next hour of movement, keep your rhythm, and leave the waiting list to us.</p></div>
      <div class="poster-footer"><span><b>01</b> Choose a session</span><span><b>02</b> Show your code</span></div>
    </section>
    <section class="auth-panel"><div class="auth-card">
      <span class="eyebrow">Welcome to Pulse</span><h2>${isLogin ? 'Good to see you.' : 'Start your rhythm.'}</h2>
      <p>${isLogin ? 'Sign in to manage your classes and find your next session.' : 'A few details and your first session is only a click away.'}</p>
      <nav class="tabs" aria-label="Account pages"><a class="${isLogin ? 'active' : ''}" href="#login">Sign in</a><a class="${!isLogin ? 'active' : ''}" href="#register">Create account</a></nav>
      <form id="auth-form" novalidate>
        ${!isLogin ? field('name', 'Your name', 'text', 'Alex Morgan', 'autocomplete="name"') : ''}
        ${field('email', 'Email address', 'email', 'you@example.com', 'autocomplete="email"')}
        ${field('password', 'Password', 'password', 'At least 10 characters', isLogin ? 'autocomplete="current-password"' : 'autocomplete="new-password"')}
        <div id="form-alert" class="form-alert" role="alert"></div>
        <button class="button primary auth-submit" type="submit">${isLogin ? 'Sign in to Pulse' : 'Create my account'} <span aria-hidden="true">→</span></button>
      </form>
      <p class="hint">Demo member: <b>alex@pulsegym.test</b><br />Password: <b>MoveStrong2026!</b></p>
    </div></section>
  </main>`;
  document.querySelector('#auth-form').addEventListener('submit', event => submitAuth(event, isLogin));
}
function field(name, label, type, placeholder, extra = '') { return `<div class="field"><label for="${name}">${label}</label><input id="${name}" name="${name}" type="${type}" placeholder="${placeholder}" ${extra} required /><span class="field-error" id="${name}-error"></span></div>`; }
function formError(name, message = '') { const input = document.querySelector(`#${name}`), messageEl = document.querySelector(`#${name}-error`); if (input) input.setAttribute('aria-invalid', message ? 'true' : 'false'); if (messageEl) messageEl.textContent = message; }
async function submitAuth(event, isLogin) {
  event.preventDefault(); const form = event.currentTarget; const button = form.querySelector('button'); const payload = Object.fromEntries(new FormData(form));
  ['name','email','password'].forEach(key => formError(key)); document.querySelector('#form-alert').textContent = '';
  let invalid = false;
  if (!isLogin && payload.name.trim().length < 2) { formError('name', 'Enter at least 2 characters.'); invalid = true; }
  if (!/^\S+@\S+\.\S+$/.test(payload.email)) { formError('email', 'Enter a valid email address.'); invalid = true; }
  if (payload.password.length < 10) { formError('password', 'Use at least 10 characters.'); invalid = true; }
  if (invalid) return;
  button.disabled = true; button.innerHTML = '<span class="loading">Please wait</span>';
  try { const data = await api(`/api/auth/${isLogin ? 'login' : 'register'}`, { method:'POST', body: JSON.stringify(payload) }); setAuth(data.token, data.user); location.hash = data.user.role === 'admin' ? '#admin' : '#sessions'; }
  catch (error) { if (error.fields) Object.entries(error.fields).forEach(([key, value]) => formError(key, value)); document.querySelector('#form-alert').textContent = error.message; button.disabled = false; button.textContent = isLogin ? 'Sign in to Pulse →' : 'Create my account →'; }
}

function shell(view) {
  const route = activeRoute(); const admin = state.user.role === 'admin';
  const links = [{ key:'sessions', label:'Sessions', icon:'calendar' }, ...(!admin ? [{ key:'bookings', label:'My bookings', icon:'ticket' }] : []), ...(admin ? [{ key:'admin', label:'Gym desk', icon:'settings' }] : [])];
  app.innerHTML = `<div class="app-shell">
    <aside class="sidebar"><a class="logo" href="#sessions"><i class="logo-mark"></i>pulse</a>
      <nav class="nav" aria-label="Main navigation">${links.map(link => `<a class="nav-link ${route === link.key ? 'active' : ''}" href="#${link.key}">${icon(link.icon)}<span>${link.label}</span></a>`).join('')}</nav>
      <div class="sidebar-bottom"><span class="account-name">${esc(state.user.name)}</span><span class="account-role">${esc(state.user.role)}</span><button class="sign-out" id="signout">Sign out →</button></div>
    </aside>
    <main class="main"><header class="topbar"><span class="mobile-brand logo"><i class="logo-mark"></i>pulse</span><span class="today">${todayText()}</span><span class="live">Live updates</span></header><div id="view" class="content">${view}</div></main>
  </div>`;
  document.querySelector('#signout').addEventListener('click', () => signOut());
}
function heading(kicker, title, description = '') { return `<div class="page-heading"><div><span class="eyebrow">${kicker}</span><h1>${title}</h1></div>${description ? `<p>${description}</p>` : ''}</div>`; }
function loading(label = 'Loading your sessions…') { return `<div class="state"><span class="loading">${label}</span></div>`; }
function empty(title, copy, button = '') { return `<div class="state"><strong>${title}</strong><span>${copy}</span>${button}</div>`; }
function metric(label, value) { return `<article class="metric"><small>${label}</small><strong>${value}</strong></article>`; }

async function sessionsPage() {
  shell(`${heading('Your schedule', 'Find your next hour.', 'Small groups, properly paced. Sessions update automatically while you are here.')}<div class="metric-row" id="session-metrics">${metric('Upcoming sessions', '—')}${metric('Open seats', '—')}${metric('Your bookings', '—')}</div><div class="toolbar"><div class="date-filter"><label for="date-filter">Filter by date</label><input class="filter-input" id="date-filter" type="date" /></div><span class="refresh-copy">Refreshes every 20 seconds</span></div><section id="sessions-area">${loading()}</section>`);
  document.querySelector('#date-filter').addEventListener('change', () => loadSessions());
  await loadSessions();
  state.poll = setInterval(() => { if (activeRoute() === 'sessions') loadSessions(false); }, 20000);
}
async function loadSessions(showLoading = true) {
  const area = document.querySelector('#sessions-area'); if (!area) return;
  if (showLoading) area.innerHTML = loading();
  const date = document.querySelector('#date-filter')?.value;
  try {
    const data = await api(`/api/sessions${date ? `?date=${encodeURIComponent(date)}` : ''}`); state.sessions = data.sessions;
    renderSessionMetrics(); renderSessionGrid();
  } catch (error) { area.innerHTML = empty('Couldn’t load sessions.', esc(error.message), '<button class="button ghost small" id="retry-sessions">Try again</button>'); document.querySelector('#retry-sessions')?.addEventListener('click', () => loadSessions()); }
}
function renderSessionMetrics() {
  const target = document.querySelector('#session-metrics'); if (!target) return;
  const open = state.sessions.reduce((sum, s) => sum + s.seatsRemaining, 0); const booked = state.sessions.filter(s => s.myStatus === 'booked').length;
  target.innerHTML = `${metric('Upcoming sessions', state.sessions.length)}${metric('Open seats', open)}${metric('Your bookings', booked)}`;
}
function renderSessionGrid() {
  const area = document.querySelector('#sessions-area'); if (!area) return;
  if (!state.sessions.length) { area.innerHTML = empty('No sessions match that day.', 'Try another date, or check back soon for new classes.'); return; }
  area.innerHTML = `<div class="session-grid">${state.sessions.map(sessionCard).join('')}</div>`;
  area.querySelectorAll('[data-action]').forEach(button => button.addEventListener('click', handleSessionAction));
}
function sessionCard(s) {
  const full = s.seatsRemaining === 0; const pct = Math.min(100, Math.round((s.confirmed / s.capacity) * 100));
  let actions;
  if (state.user.role === 'admin') actions = '<p class="waitlist-note">Use Gym desk to manage this session.</p>';
  else if (s.myStatus === 'booked') actions = '<button class="button secondary" disabled>Booked ✓</button>';
  else if (s.myStatus === 'waitlisted') actions = `<button class="button ghost" data-action="leave-waitlist" data-id="${s.id}">Leave waitlist</button><p class="waitlist-note">You’re in the queue.</p>`;
  else if (full) actions = `<button class="button primary" data-action="waitlist" data-id="${s.id}">Join waitlist</button><p class="waitlist-note">${s.waitlistCount ? `${s.waitlistCount} waiting` : 'Be first in line'}</p>`;
  else actions = `<button class="button primary" data-action="book" data-id="${s.id}">Book this session <span aria-hidden="true">→</span></button>`;
  return `<article class="session-card ${full ? 'full' : ''}" id="session-${s.id}"><span class="day">${humanDate(s.startsAt)}</span><h2>${clock(s.startsAt)}</h2><p class="time">One hour · Studio floor</p><div class="seat-block"><div class="seats"><span class="status-chip ${full ? 'full' : 'open'}">${full ? 'Waitlist' : 'Open'}</span><strong>${s.seatsRemaining} ${s.seatsRemaining === 1 ? 'spot' : 'spots'}</strong></div><div class="seat-meter" aria-label="${s.seatsRemaining} seats remaining"><i style="width:${pct}%"></i></div></div><div class="session-actions">${actions}</div></article>`;
}
async function handleSessionAction(event) {
  const button = event.currentTarget; const id = button.dataset.id; const action = button.dataset.action; const card = document.querySelector(`#session-${id}`); const original = card?.innerHTML;
  button.disabled = true; button.innerHTML = '<span class="loading">Working</span>';
  if (action === 'book') { const current = state.sessions.find(x => x.id === Number(id)); if (current) { current.seatsRemaining--; current.confirmed++; renderSessionMetrics(); } }
  try {
    if (action === 'book') { await api(`/api/sessions/${id}/book`, { method:'POST' }); showToast('Booked. Your check-in code is in My bookings.'); }
    if (action === 'waitlist') { await api(`/api/sessions/${id}/waitlist`, { method:'POST' }); showToast('You’re on the waitlist. We’ll promote you automatically if a seat opens.'); }
    if (action === 'leave-waitlist') { await api(`/api/sessions/${id}/waitlist`, { method:'DELETE' }); showToast('You left the waitlist.'); }
    await loadSessions(false);
  } catch (error) { if (original && card) card.innerHTML = original; showToast(error.message, 'error'); await loadSessions(false); }
}

async function bookingsPage() {
  shell(`${heading('Your sessions', 'Your booking wallet.', 'Your unique check-in code appears below. Keep it handy at the front desk.')}<section id="bookings-area">${loading('Loading your bookings…')}</section>`);
  try {
    const { bookings } = await api('/api/bookings/me'); const area = document.querySelector('#bookings-area');
    if (!bookings.length) { area.innerHTML = empty('Nothing booked yet.', 'Find a session that works for you and claim your spot.', '<a class="button primary small" href="#sessions">Browse sessions</a>'); return; }
    area.innerHTML = `<div class="booking-list">${bookings.map(b => `<article class="booking-card"><div class="booking-time">${humanDate(b.startsAt)}<small>${clock(b.startsAt)} · One hour session</small></div><div class="code-box"><small>Your check-in code</small><div class="code">${esc(b.code)}</div></div><div class="booking-side"><span class="status-chip open">Confirmed</span><br /><button class="button danger small" data-cancel="${b.id}">Cancel</button></div></article>`).join('')}</div>`;
    area.querySelectorAll('[data-cancel]').forEach(button => button.addEventListener('click', () => cancelBooking(button)));
  } catch (error) { document.querySelector('#bookings-area').innerHTML = empty('Couldn’t load bookings.', esc(error.message), '<button class="button ghost small" id="retry-bookings">Try again</button>'); document.querySelector('#retry-bookings')?.addEventListener('click', bookingsPage); }
}
async function cancelBooking(button) {
  const label = button.textContent; button.disabled = true; button.textContent = 'Cancelling…';
  try { await api(`/api/bookings/${button.dataset.cancel}`, { method:'DELETE' }); showToast('Booking cancelled. The next waiting member has been offered the seat.'); bookingsPage(); }
  catch (error) { button.disabled = false; button.textContent = label; showToast(error.message, 'error'); }
}

async function adminPage() {
  shell(`${heading('Gym desk', 'Run a smooth room.', 'Create sessions, review your roster and check members in from one calm, focused desk.')}<div class="admin-layout"><div><section class="admin-card"><span class="eyebrow">New session</span><h2>Open a one-hour class</h2><p>Every session has exactly 20 places and starts on the hour.</p><form id="new-session" novalidate><div class="field"><label for="startsAt">Start date and hour</label><input id="startsAt" type="datetime-local" step="3600" required /><span id="startsAt-error" class="field-error"></span></div><button class="button primary" type="submit">Create session →</button></form></section><section class="admin-card checkin"><span class="eyebrow">Front desk</span><h2>Check a member in</h2><p>Enter the six-character code from their app. Codes only work during the session hour.</p><form id="checkin-form"><div class="field"><label for="checkin-code">Check-in code</label><input id="checkin-code" maxlength="6" placeholder="7XKP2Q" autocomplete="off" required /></div><button class="button primary" type="submit">Mark present</button></form><div class="checkin-result hidden" id="checkin-result"></div></section></div><section class="admin-card admin-bookings"><span class="eyebrow">Session roster</span><h2>Who’s coming?</h2><p>Choose a session to see confirmed members, their codes and everyone in the waitlist.</p><label class="hidden" for="session-select">Select a session</label><select id="session-select" class="admin-select"><option value="">Loading sessions…</option></select><div id="roster-area" class="state"><span class="loading">Loading roster</span></div></section></div>`);
  const input = document.querySelector('#startsAt'); input.min = localInputDate() + 'T00:00';
  document.querySelector('#new-session').addEventListener('submit', createSession);
  document.querySelector('#checkin-form').addEventListener('submit', checkIn);
  try {
    const { sessions } = await api('/api/sessions'); state.sessions = sessions; const select = document.querySelector('#session-select');
    if (!sessions.length) { select.innerHTML = '<option value="">No upcoming sessions</option>'; document.querySelector('#roster-area').innerHTML = empty('No sessions yet.', 'Create the first one using the form.'); return; }
    select.innerHTML = sessions.map(s => `<option value="${s.id}">${esc(sessionLabel(s))} · ${s.seatsRemaining} spots</option>`).join(''); select.addEventListener('change', () => loadRoster(select.value)); await loadRoster(select.value);
  } catch (error) { document.querySelector('#roster-area').innerHTML = empty('Couldn’t load the desk.', esc(error.message)); }
}
async function loadRoster(id) {
  const area = document.querySelector('#roster-area'); if (!area || !id) return; area.innerHTML = loading('Loading session roster…');
  try {
    const data = await api(`/api/admin/sessions/${id}/bookings`); const { session, bookings, waitlist } = data;
    area.className = ''; area.innerHTML = `<div class="roster-header"><h3>${bookings.length} / ${session.capacity} confirmed</h3><span class="status-chip ${session.seatsRemaining ? 'open' : 'full'}">${session.seatsRemaining} spots left</span></div>${bookings.length ? `<div class="roster">${bookings.map(b => `<div class="roster-item"><span><b>${esc(b.name)}</b><small>${esc(b.email)} · <span class="roster-code">${esc(b.code)}</span></small></span>${b.checkedInAt ? '<span class="checked">PRESENT ✓</span>' : '<span class="status-chip">Expected</span>'}</div>`).join('')}</div>` : empty('No confirmed bookings.', 'This session is still wide open.')}${waitlist.length ? `<div class="waitlist"><span class="eyebrow">Waitlist · ${waitlist.length}</span><ul>${waitlist.map((w, index) => `<li><span>${index + 1}. ${esc(w.name)}</span><span>${esc(w.email)}</span></li>`).join('')}</ul></div>` : ''}`;
  } catch (error) { area.className = 'state'; area.innerHTML = `<strong>Couldn’t load this roster.</strong><span>${esc(error.message)}</span>`; }
}
async function createSession(event) {
  event.preventDefault(); const input = document.querySelector('#startsAt'); const errorEl = document.querySelector('#startsAt-error'); const button = event.currentTarget.querySelector('button'); errorEl.textContent = '';
  if (!input.value || new Date(input.value) <= new Date() || new Date(input.value).getMinutes() !== 0) { errorEl.textContent = 'Choose a future whole hour.'; return; }
  button.disabled = true; button.innerHTML = '<span class="loading">Creating</span>';
  try { await api('/api/sessions', {method:'POST', body: JSON.stringify({startsAt: input.value + ':00'})}); showToast('Session created. It is now visible to members.'); adminPage(); }
  catch (error) { errorEl.textContent = error.fields?.startsAt || error.message; button.disabled = false; button.textContent = 'Create session →'; }
}
async function checkIn(event) {
  event.preventDefault(); const input = document.querySelector('#checkin-code'); const button = event.currentTarget.querySelector('button'); const result = document.querySelector('#checkin-result'); result.classList.add('hidden'); input.value = input.value.toUpperCase().replace(/[^A-Z0-9]/g, '');
  if (input.value.length !== 6) { result.textContent = 'Enter the complete six-character code.'; result.classList.remove('hidden'); return; }
  button.disabled = true; button.innerHTML = '<span class="loading">Checking</span>';
  try { const data = await api('/api/admin/check-in', {method:'POST', body: JSON.stringify({code: input.value})}); result.textContent = `Checked in: ${data.booking.name} (${data.booking.email})`; result.classList.remove('hidden'); input.value = ''; const id = document.querySelector('#session-select').value; if (id) loadRoster(id); }
  catch (error) { result.textContent = error.message; result.classList.remove('hidden'); }
  finally { button.disabled = false; button.textContent = 'Mark present'; }
}

async function render() {
  clearPoll(); let route = activeRoute();
  if (!state.user) { authPage(route === 'register' ? 'register' : 'login'); return; }
  if (!['sessions','bookings','admin'].includes(route)) { location.hash = state.user.role === 'admin' ? '#admin' : '#sessions'; return; }
  if (route === 'admin' && state.user.role !== 'admin') { showToast('The gym desk is for admins only.', 'error'); location.hash = '#sessions'; return; }
  if (route === 'bookings' && state.user.role !== 'member') { location.hash = '#admin'; return; }
  if (route === 'sessions') await sessionsPage();
  if (route === 'bookings') await bookingsPage();
  if (route === 'admin') await adminPage();
}
window.addEventListener('hashchange', render);
render();
