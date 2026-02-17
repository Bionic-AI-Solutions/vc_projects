"""Kong Header Proxy - Sidecar container that captures Kong auth headers.

This proxy:
1. Receives requests on port 8000 (from Kong)
2. Captures X-Consumer-Username or X-Consumer-Custom-ID headers
3. Stores per-session email mappings in Redis keyed by ADK session_id
4. Forwards requests to the main ADK app on port 8001
"""

import os
import json
import re
import logging
from fastapi import FastAPI, Request, Response
from fastapi.responses import StreamingResponse
import httpx
import redis.asyncio.cluster as aioredis_cluster

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("KongProxy")

# Redis connection for per-user email storage
REDIS_HOST = os.environ.get("REDIS_HOST", "redis-cluster.redis.svc.cluster.local")
REDIS_PORT = int(os.environ.get("REDIS_PORT", "6379"))
EMAIL_TTL_SECONDS = 86400  # 24 hours
REDIS_CONFIG_KEY = "model_config"

# Agent configuration metadata (used by config UI and API)
AGENT_CONFIG_META = [
    {"key": "MODEL_ROUTER", "label": "Router Agent", "default": "gemini-3-flash-preview"},
    {"key": "MODEL_COMPANY_RESEARCH", "label": "Company Research", "default": "gemini-3-flash-preview"},
    {"key": "MODEL_MARKET_ANALYSIS", "label": "Market Analysis", "default": "gemini-3-flash-preview"},
    {"key": "MODEL_FACT_VERIFICATION", "label": "Fact Verification (QA1)", "default": "gemini-3-flash-preview"},
    {"key": "MODEL_FINANCIAL_MODELING", "label": "Financial Modeling", "default": "gemini-3-pro-preview"},
    {"key": "MODEL_RISK_ASSESSMENT", "label": "Risk Assessment", "default": "gemini-3-pro-preview"},
    {"key": "MODEL_INVESTOR_MEMO", "label": "Investor Memo", "default": "gemini-3-pro-preview"},
    {"key": "MODEL_MEMO_QA", "label": "Memo QA (QA2)", "default": "gemini-3-pro-preview"},
    {"key": "MODEL_HTML_REPORT", "label": "HTML Report", "default": "gemini-3-flash-preview"},
    {"key": "MODEL_INFOGRAPHIC", "label": "Infographic", "default": "gemini-3-flash-preview"},
    {"key": "MODEL_PDF_REPORT", "label": "PDF Report", "default": "gemini-3-flash-preview"},
    {"key": "MODEL_TOOLS_HTML_GENERATION", "label": "Tools: HTML Generation", "default": "gemini-3-flash-preview"},
    {"key": "MODEL_TOOLS_IMAGE_GENERATION", "label": "Tools: Image Generation", "default": "gemini-3-pro-image-preview", "is_image": True},
]

AVAILABLE_MODELS_LIST = [
    {"id": "gemini-3-pro-preview", "label": "Gemini 3 Pro (Preview)", "tier": "pro"},
    {"id": "gemini-3-flash-preview", "label": "Gemini 3 Flash (Preview)", "tier": "flash"},
    {"id": "gemini-2.5-pro", "label": "Gemini 2.5 Pro", "tier": "pro"},
    {"id": "gemini-2.5-flash", "label": "Gemini 2.5 Flash", "tier": "flash"},
]

IMAGE_MODELS_LIST = [
    {"id": "gemini-3-pro-image-preview", "label": "Gemini 3 Pro Image (Preview)"},
]

# Regex to extract session_id from ADK URL paths: /apps/{app}/users/{user_id}/sessions/{session_id}
SESSION_ID_PATTERN = re.compile(r"/?apps/[^/]+/users/[^/]+/sessions/([^/]+)")

# Target ADK application
TARGET_HOST = "localhost"
TARGET_PORT = 8001

app = FastAPI(title="Kong Auth Proxy")

# JavaScript injected into the ADK Dev UI to display session names from state
# instead of raw UUIDs, and to allow renaming sessions via an edit icon.
SESSION_NAME_SCRIPT = b"""
<script>
(function() {
  var SESSION_NAME_KEY = 'session_name';
  var nameCache = {};
  var appName = '';
  var userId = '';
  var updating = false;

  function detectAppAndUser() {
    var appEl = document.querySelector('mat-select[class*="app"], .app-selector');
    if (appEl) appName = appEl.textContent.trim();
    if (!appName) appName = 'vc_due_diligence';
    userId = 'user';
  }

  function fetchSessionNames() {
    detectAppAndUser();
    fetch('/apps/' + appName + '/users/' + userId + '/sessions')
      .then(function(r) { return r.ok ? r.json() : []; })
      .then(function(sessions) {
        for (var i = 0; i < sessions.length; i++) {
          var s = sessions[i];
          if (s.state && s.state[SESSION_NAME_KEY]) {
            nameCache[s.id] = s.state[SESSION_NAME_KEY];
          }
        }
        replaceAll();
      })
      .catch(function() {});
  }

  function replaceAll() {
    if (updating) return;
    updating = true;
    try {
      // Replace session IDs in the sidebar list
      var els = document.querySelectorAll('.session-id');
      for (var i = 0; i < els.length; i++) {
        var el = els[i];
        var origId = el.getAttribute('data-original-id');
        var text = origId || el.textContent.trim();
        if (nameCache[text] && el.textContent.trim() !== nameCache[text]) {
          if (!origId) el.setAttribute('data-original-id', text);
          el.textContent = nameCache[text];
          el.title = text;
        }
        addEditButton(el);
      }
      // Replace toolbar session ID
      var toolbar = document.querySelector('.toolbar-session-id');
      if (toolbar) {
        var origTid = toolbar.getAttribute('data-original-id');
        var tid = origTid || toolbar.textContent.trim();
        if (nameCache[tid] && toolbar.textContent.trim() !== nameCache[tid]) {
          if (!origTid) toolbar.setAttribute('data-original-id', tid);
          toolbar.textContent = nameCache[tid];
          toolbar.title = 'Session: ' + tid;
        }
      }
    } finally {
      updating = false;
    }
  }

  function addEditButton(sessionIdEl) {
    var parent = sessionIdEl.parentElement;
    if (!parent || parent.querySelector('.session-rename-btn')) return;
    var btn = document.createElement('span');
    btn.className = 'session-rename-btn';
    btn.textContent = '\\u270E';
    btn.title = 'Rename session';
    btn.style.cssText = 'cursor:pointer;font-size:13px;opacity:0.4;margin-left:6px;transition:opacity 0.2s;';
    btn.onmouseenter = function() { btn.style.opacity = '1'; };
    btn.onmouseleave = function() { btn.style.opacity = '0.4'; };
    btn.addEventListener('click', function(e) {
      e.stopPropagation();
      e.preventDefault();
      var uuid = sessionIdEl.getAttribute('data-original-id') || sessionIdEl.textContent.trim();
      var currentName = nameCache[uuid] || uuid;
      var newName = prompt('Rename session:', currentName);
      if (newName && newName.trim() && newName.trim() !== currentName) {
        fetch('/api/sessions/' + encodeURIComponent(uuid) + '/name', {
          method: 'PATCH',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({name: newName.trim(), app_name: appName, user_id: userId})
        }).then(function(r) {
          if (r.ok) {
            nameCache[uuid] = newName.trim();
            sessionIdEl.textContent = newName.trim();
            var toolbar = document.querySelector('.toolbar-session-id');
            if (toolbar && toolbar.getAttribute('data-original-id') === uuid) {
              toolbar.textContent = newName.trim();
            }
          }
        });
      }
    });
    parent.appendChild(btn);
  }

  // Debounced observer to avoid rapid re-entry
  var debounceTimer = null;
  var observer = new MutationObserver(function() {
    if (updating) return;
    clearTimeout(debounceTimer);
    debounceTimer = setTimeout(replaceAll, 300);
  });

  function init() {
    fetchSessionNames();
    observer.observe(document.body, { childList: true, subtree: true });
    setInterval(fetchSessionNames, 8000);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
</script>
"""

# JavaScript for model configuration gear icon + modal overlay
MODEL_CONFIG_SCRIPT = b"""
<script>
(function() {
  var API = '/api/config/models';

  function createBtn() {
    if (document.getElementById('mc-btn')) return;
    var b = document.createElement('button');
    b.id = 'mc-btn';
    b.innerHTML = '&#9881;';
    b.title = 'Model Configuration';
    b.style.cssText = 'position:fixed;top:8px;right:16px;z-index:10000;background:transparent;border:none;color:#b0b0b0;font-size:22px;cursor:pointer;padding:4px 8px;border-radius:4px;transition:all 0.2s;';
    b.onmouseenter = function() { b.style.color = '#fff'; b.style.background = 'rgba(255,255,255,0.1)'; };
    b.onmouseleave = function() { b.style.color = '#b0b0b0'; b.style.background = 'transparent'; };
    b.onclick = openModal;
    document.body.appendChild(b);
  }

  function openModal() {
    if (document.getElementById('mc-ov')) return;
    fetch(API).then(function(r) { return r.json(); }).then(renderModal)
      .catch(function(e) { alert('Config load failed: ' + e); });
  }

  function renderModal(data) {
    var ov = document.createElement('div');
    ov.id = 'mc-ov';
    ov.style.cssText = 'position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,0.6);z-index:10001;display:flex;align-items:center;justify-content:center;';
    ov.onclick = function(e) { if (e.target === ov) closeModal(); };

    var m = document.createElement('div');
    m.style.cssText = 'background:#1e1e2e;border-radius:12px;padding:28px 32px;min-width:540px;max-width:660px;max-height:85vh;overflow-y:auto;box-shadow:0 20px 60px rgba(0,0,0,0.5);color:#e0e0e0;font-family:-apple-system,BlinkMacSystemFont,sans-serif;';

    var hdr = document.createElement('div');
    hdr.style.cssText = 'display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;';
    var t = document.createElement('h2');
    t.textContent = 'Model Configuration';
    t.style.cssText = 'margin:0;font-size:20px;font-weight:600;color:#fff;';
    var xb = document.createElement('button');
    xb.innerHTML = '&times;';
    xb.style.cssText = 'background:none;border:none;color:#888;font-size:24px;cursor:pointer;padding:0 4px;';
    xb.onclick = closeModal;
    hdr.appendChild(t);
    hdr.appendChild(xb);
    m.appendChild(hdr);

    var sub = document.createElement('p');
    sub.textContent = 'Select models for each pipeline agent. Changes apply to subsequent runs.';
    sub.style.cssText = 'margin:0 0 18px;font-size:13px;color:#888;';
    m.appendChild(sub);

    var tbl = document.createElement('div');
    tbl.style.cssText = 'display:flex;flex-direction:column;gap:8px;';

    for (var i = 0; i < data.agents.length; i++) {
      var ag = data.agents[i];
      var row = document.createElement('div');
      row.style.cssText = 'display:flex;align-items:center;justify-content:space-between;padding:10px 14px;background:#2a2a3e;border-radius:8px;';

      var ld = document.createElement('div');
      ld.style.cssText = 'display:flex;flex-direction:column;min-width:180px;';
      var nm = document.createElement('span');
      nm.textContent = ag.label;
      nm.style.cssText = 'font-size:14px;font-weight:500;';
      var df = document.createElement('span');
      df.textContent = 'default: ' + ag.default_model.replace('gemini-', '').replace('-preview', '');
      df.style.cssText = 'font-size:11px;color:#666;margin-top:2px;';
      ld.appendChild(nm);
      ld.appendChild(df);
      row.appendChild(ld);

      var sel = document.createElement('select');
      sel.className = 'mc-sel';
      sel.dataset.key = ag.key;
      sel.style.cssText = 'background:#383850;color:#e0e0e0;border:1px solid #4a4a6a;border-radius:6px;padding:6px 10px;font-size:13px;min-width:210px;cursor:pointer;outline:none;';
      var ml = ag.is_image_model ? data.image_models : data.available_models;
      for (var j = 0; j < ml.length; j++) {
        var o = document.createElement('option');
        o.value = ml[j].id;
        o.textContent = ml[j].label;
        if (ml[j].id === ag.current_model) o.selected = true;
        sel.appendChild(o);
      }
      row.appendChild(sel);
      tbl.appendChild(row);
    }
    m.appendChild(tbl);

    var br = document.createElement('div');
    br.style.cssText = 'display:flex;justify-content:space-between;margin-top:22px;';
    var rb = document.createElement('button');
    rb.textContent = 'Reset to Defaults';
    rb.style.cssText = 'background:transparent;color:#f87171;border:1px solid rgba(248,113,113,0.4);border-radius:6px;padding:8px 16px;font-size:13px;cursor:pointer;';
    rb.onclick = doReset;
    var rd = document.createElement('div');
    rd.style.cssText = 'display:flex;gap:10px;';
    var cb = document.createElement('button');
    cb.textContent = 'Cancel';
    cb.style.cssText = 'background:#383850;color:#e0e0e0;border:none;border-radius:6px;padding:8px 20px;font-size:13px;cursor:pointer;';
    cb.onclick = closeModal;
    var sb = document.createElement('button');
    sb.id = 'mc-save';
    sb.textContent = 'Save';
    sb.style.cssText = 'background:#6366f1;color:#fff;border:none;border-radius:6px;padding:8px 24px;font-size:13px;cursor:pointer;font-weight:500;';
    sb.onclick = doSave;
    rd.appendChild(cb);
    rd.appendChild(sb);
    br.appendChild(rb);
    br.appendChild(rd);
    m.appendChild(br);

    var st = document.createElement('div');
    st.id = 'mc-st';
    st.style.cssText = 'margin-top:12px;font-size:12px;text-align:center;min-height:18px;color:#888;';
    m.appendChild(st);

    ov.appendChild(m);
    document.body.appendChild(ov);
  }

  function closeModal() { var e = document.getElementById('mc-ov'); if (e) e.remove(); }

  function stat(msg, ok) {
    var e = document.getElementById('mc-st');
    if (e) { e.textContent = msg; e.style.color = ok ? '#4ade80' : '#f87171'; }
  }

  function doSave() {
    var o = {}, s = document.querySelectorAll('.mc-sel');
    for (var i = 0; i < s.length; i++) o[s[i].dataset.key] = s[i].value;
    var btn = document.getElementById('mc-save');
    if (btn) { btn.disabled = true; btn.textContent = 'Saving...'; }
    fetch(API, { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(o) })
      .then(function(r) { if (r.ok) { stat('Saved!', true); setTimeout(closeModal, 1000); } else stat('Save failed', false); })
      .catch(function(e) { stat('Error: ' + e, false); })
      .finally(function() { if (btn) { btn.disabled = false; btn.textContent = 'Save'; } });
  }

  function doReset() {
    if (!confirm('Reset all models to defaults?')) return;
    fetch(API + '/reset', { method: 'POST' })
      .then(function(r) { if (r.ok) { stat('Reset!', true); setTimeout(function() { closeModal(); openModal(); }, 800); } else stat('Reset failed', false); })
      .catch(function(e) { stat('Error: ' + e, false); });
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', function() { setTimeout(createBtn, 500); });
  else setTimeout(createBtn, 500);
})();
</script>
"""

# Persistent client for connection reuse
http_client = httpx.AsyncClient(
    timeout=httpx.Timeout(connect=10.0, read=600.0, write=30.0, pool=10.0),
    limits=httpx.Limits(max_connections=100, max_keepalive_connections=20),
)

# Redis cluster client
redis_client = aioredis_cluster.RedisCluster(
    host=REDIS_HOST, port=REDIS_PORT, decode_responses=True
)


async def save_session_email(session_id: str, email: str):
    """Save user email to Redis, keyed by ADK session_id."""
    try:
        key = f"session_email:{session_id}"
        await redis_client.set(key, email, ex=EMAIL_TTL_SECONDS)
        logger.info(f"Saved email mapping: session {session_id} -> {email}")
    except Exception as e:
        logger.error(f"Error saving email to Redis: {e}")


def extract_session_id_from_path(path: str) -> str:
    """Extract session_id from ADK URL path pattern."""
    match = SESSION_ID_PATTERN.search(path)
    if match:
        return match.group(1)
    return ""


def extract_session_id_from_body(body: bytes) -> str:
    """Extract session_id from JSON request body (for /run, /run_sse endpoints)."""
    try:
        if body:
            data = json.loads(body)
            return data.get("session_id", "")
    except (json.JSONDecodeError, AttributeError):
        pass
    return ""


@app.patch("/api/sessions/{session_id}/name")
async def rename_session(session_id: str, request: Request):
    """Rename a session by updating its state with a new session_name."""
    try:
        body = await request.json()
        new_name = body.get("name", "").strip()
        if not new_name:
            return Response(content='{"error": "name is required"}', status_code=400,
                            media_type="application/json")

        app_name = body.get("app_name", "vc_due_diligence")
        user_id = body.get("user_id", "user")

        url = f"http://{TARGET_HOST}:{TARGET_PORT}/apps/{app_name}/users/{user_id}/sessions/{session_id}"
        resp = await http_client.request(
            method="PATCH",
            url=url,
            json={"state_delta": {"session_name": new_name}}
        )
        return Response(
            content=resp.content,
            status_code=resp.status_code,
            headers=dict(resp.headers)
        )
    except Exception as e:
        logger.error(f"Error renaming session: {e}")
        return Response(content=f'{{"error": "{str(e)}"}}', status_code=500,
                        media_type="application/json")


@app.get("/api/config/models")
async def get_model_config():
    """Return current model configuration and available models."""
    try:
        overrides_json = await redis_client.get(REDIS_CONFIG_KEY)
        overrides = json.loads(overrides_json) if overrides_json else {}
    except Exception as e:
        logger.warning(f"Could not read config from Redis: {e}")
        overrides = {}

    agents = []
    for meta in AGENT_CONFIG_META:
        current = overrides.get(meta["key"], meta["default"])
        agents.append({
            "key": meta["key"],
            "label": meta["label"],
            "current_model": current,
            "default_model": meta["default"],
            "is_image_model": meta.get("is_image", False),
        })
    return {
        "agents": agents,
        "available_models": AVAILABLE_MODELS_LIST,
        "image_models": IMAGE_MODELS_LIST,
    }


@app.post("/api/config/models")
async def save_model_config(request: Request):
    """Save model configuration overrides to Redis."""
    try:
        overrides = await request.json()
        await redis_client.set(REDIS_CONFIG_KEY, json.dumps(overrides))
        logger.info(f"Saved model config to Redis: {overrides}")
        return {"status": "ok", "message": "Configuration saved"}
    except Exception as e:
        logger.error(f"Error saving model config: {e}")
        return Response(content=f'{{"error": "{str(e)}"}}', status_code=500,
                        media_type="application/json")


@app.post("/api/config/models/reset")
async def reset_model_config():
    """Reset all model overrides to defaults."""
    try:
        await redis_client.delete(REDIS_CONFIG_KEY)
        logger.info("Model config reset to defaults")
        return {"status": "ok", "message": "Reset to defaults"}
    except Exception as e:
        logger.error(f"Error resetting model config: {e}")
        return Response(content=f'{{"error": "{str(e)}"}}', status_code=500,
                        media_type="application/json")


@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"])
async def proxy(request: Request, path: str):
    """Proxy all requests to the target application."""

    # Extract user email from Kong headers
    user_email = (
        request.headers.get("X-Consumer-Username") or
        request.headers.get("X-Consumer-Custom-ID") or
        request.headers.get("x-consumer-username") or
        request.headers.get("x-consumer-custom-id") or
        ""
    )

    # Prepare headers (exclude host and content-length for proxying)
    headers = dict(request.headers)
    headers.pop('host', None)
    headers.pop('content-length', None)

    # Read request body for methods that have one
    body = None
    if request.method in ["POST", "PUT", "PATCH"]:
        body = await request.body()

    # Extract session_id and save per-session email mapping to Redis
    if user_email:
        session_id = extract_session_id_from_path(path)
        if not session_id and body:
            session_id = extract_session_id_from_body(body)

        if session_id:
            logger.info(f"Captured Kong header - User: {user_email}, Session: {session_id}")
            await save_session_email(session_id, user_email)
        else:
            logger.debug(f"Have email {user_email} but no session_id in request")
    else:
        logger.debug("No Kong authentication headers found")

    # Construct target URL
    url = f"http://{TARGET_HOST}:{TARGET_PORT}/{path}"
    if request.url.query:
        url = f"{url}?{request.url.query}"

    logger.debug(f"Proxying {request.method} {url}")

    # Check if this is likely an SSE endpoint
    is_sse_request = (
        'text/event-stream' in request.headers.get('accept', '') or
        path in ('run_sse', 'run')
    )

    try:
        if is_sse_request:
            # Use streaming for SSE - don't buffer the response
            req = http_client.build_request(
                method=request.method,
                url=url,
                headers=headers,
                content=body
            )
            response = await http_client.send(req, stream=True)

            content_type = response.headers.get('content-type', '')

            if 'text/event-stream' in content_type:
                async def stream_sse():
                    try:
                        async for chunk in response.aiter_bytes():
                            yield chunk
                    finally:
                        await response.aclose()

                # Pass through SSE headers, set proper streaming headers
                resp_headers = dict(response.headers)
                resp_headers.pop('content-length', None)
                resp_headers.pop('transfer-encoding', None)
                resp_headers['cache-control'] = 'no-cache'
                resp_headers['x-accel-buffering'] = 'no'

                return StreamingResponse(
                    stream_sse(),
                    status_code=response.status_code,
                    headers=resp_headers,
                    media_type='text/event-stream',
                )
            else:
                # Not SSE after all, read and return normally
                content = await response.aread()
                await response.aclose()
                return Response(
                    content=content,
                    status_code=response.status_code,
                    headers=dict(response.headers)
                )
        else:
            # Non-SSE: regular buffered request
            response = await http_client.request(
                method=request.method,
                url=url,
                headers=headers,
                content=body
            )

            content = response.content
            resp_headers = dict(response.headers)

            # Inject session-naming script into Dev UI HTML pages
            content_type = response.headers.get('content-type', '')
            if 'text/html' in content_type and b'</body>' in content:
                content = content.replace(b'</body>', SESSION_NAME_SCRIPT + MODEL_CONFIG_SCRIPT + b'</body>')
                resp_headers['content-length'] = str(len(content))

            return Response(
                content=content,
                status_code=response.status_code,
                headers=resp_headers
            )

    except httpx.ConnectError:
        logger.error(f"Failed to connect to {TARGET_HOST}:{TARGET_PORT}")
        return Response(
            content="Backend service unavailable",
            status_code=503
        )
    except Exception as e:
        logger.error(f"Proxy error: {e}")
        return Response(
            content=f"Proxy error: {str(e)}",
            status_code=500
        )


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "healthy", "service": "kong-proxy"}


@app.on_event("shutdown")
async def shutdown():
    await http_client.aclose()
    await redis_client.aclose()


if __name__ == "__main__":
    import uvicorn

    logger.info(f"Starting Kong Proxy on port 8000")
    logger.info(f"Forwarding to {TARGET_HOST}:{TARGET_PORT}")

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        log_level="info"
    )
