/**
 * REST API client for the Volley Overlay Control backend.
 */

const BASE_URL = '/api/v1';

let apiKey = null;

export function setApiKey(key) {
  apiKey = key;
}

function headers() {
  const h = { 'Content-Type': 'application/json' };
  if (apiKey) h['Authorization'] = `Bearer ${apiKey}`;
  return h;
}

async function request(method, path, body = null) {
  const opts = { method, headers: headers() };
  if (body !== null) {
    opts.body = JSON.stringify(body);
  }
  const res = await fetch(`${BASE_URL}${path}`, opts);
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`API ${method} ${path} failed (${res.status}): ${text}`);
  }
  return res.json();
}

// Session
export function initSession(oid, opts = {}) {
  return request('POST', '/session/init', { oid, ...opts });
}

// State queries
export function getState(oid) {
  return request('GET', `/state?oid=${encodeURIComponent(oid)}`);
}

export function getConfig(oid) {
  return request('GET', `/config?oid=${encodeURIComponent(oid)}`);
}

export function getCustomization(oid) {
  return request('GET', `/customization?oid=${encodeURIComponent(oid)}`);
}

// Game actions
export function addPoint(oid, team, undo = false) {
  return request('POST', `/game/add-point?oid=${encodeURIComponent(oid)}`, { team, undo });
}

export function addSet(oid, team, undo = false) {
  return request('POST', `/game/add-set?oid=${encodeURIComponent(oid)}`, { team, undo });
}

export function addTimeout(oid, team, undo = false) {
  return request('POST', `/game/add-timeout?oid=${encodeURIComponent(oid)}`, { team, undo });
}

export function changeServe(oid, team) {
  return request('POST', `/game/change-serve?oid=${encodeURIComponent(oid)}`, { team });
}

export function setScore(oid, team, setNumber, value) {
  return request('POST', `/game/set-score?oid=${encodeURIComponent(oid)}`, {
    team,
    set_number: setNumber,
    value,
  });
}

export function setSets(oid, team, value) {
  return request('POST', `/game/set-sets?oid=${encodeURIComponent(oid)}`, { team, value });
}

export function resetGame(oid) {
  return request('POST', `/game/reset?oid=${encodeURIComponent(oid)}`);
}

// Display controls
export function setVisibility(oid, visible) {
  return request('POST', `/display/visibility?oid=${encodeURIComponent(oid)}`, { visible });
}

export function setSimpleMode(oid, enabled) {
  return request('POST', `/display/simple-mode?oid=${encodeURIComponent(oid)}`, { enabled });
}

// Customization
export function updateCustomization(oid, data) {
  return request('PUT', `/customization?oid=${encodeURIComponent(oid)}`, data);
}
