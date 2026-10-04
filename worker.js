// Cloudflare Worker that serves plugins.json with the CORS headers Decky needs.
//
// Decky sends an X-Decky-Version header, which makes the browser send a CORS
// preflight first. GitHub (Pages and raw) never answers that OPTIONS request
// the way the browser wants, and Decky has no catch around the fetch, so the
// store tab just spins forever. This worker answers the preflight and passes
// the file through from GitHub. It never needs redeploying when a plugin is
// released: it serves whatever plugins.json on main currently says.
//
// Two channels: the root URL serves stable releases (plugins.json), and
// /testing serves stable plus prereleases (plugins-testing.json).

const RAW = 'https://raw.githubusercontent.com/Marshy-Madness/MadnessDeckyStore/main/';

const CORS = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Methods': 'GET, HEAD, OPTIONS',
  'Access-Control-Allow-Headers': 'X-Decky-Version',
  'Access-Control-Max-Age': '600',
};

export default {
  async fetch(request) {
    const testing = new URL(request.url).pathname.replace(/\/+$/, '') === '/testing';

    if (request.method === 'OPTIONS') {
      return new Response(null, { status: 204, headers: CORS });
    }
    if (request.method !== 'GET' && request.method !== 'HEAD') {
      return new Response('Method not allowed', { status: 405, headers: CORS });
    }

    // Short cache: a new release should show up within a minute or two.
    const file = testing ? 'plugins-testing.json' : 'plugins.json';
    const upstream = await fetch(RAW + file, { cf: { cacheTtl: 60 } });
    if (!upstream.ok) {
      return new Response(`Upstream returned ${upstream.status}`, { status: 502, headers: CORS });
    }
    return new Response(upstream.body, {
      status: 200,
      headers: { ...CORS, 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-cache' },
    });
  },
};
