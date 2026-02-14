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
                content = content.replace(b'</body>', SESSION_NAME_SCRIPT + b'</body>')
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
