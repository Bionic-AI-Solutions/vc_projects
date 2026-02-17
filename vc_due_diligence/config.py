"""Model configuration for the Due Diligence Pipeline.

Each agent's model can be overridden via:
1. Environment variable (in .env or K8s configmap) - static, requires restart
2. Web UI config modal (stored in Redis) - runtime, no restart needed

Available models (Feb 2026):
  gemini-3-pro-preview       ($2/$12 per 1M tokens) - best reasoning
  gemini-3-flash-preview     ($0.50/$3) - fast, near-pro quality
  gemini-2.5-pro             ($1.25/$10) - stable, strong reasoning
  gemini-2.5-flash           ($0.30/$2.50) - cheapest, fast
  gemini-3-pro-image-preview - image generation
"""

import os
import json
import logging

logger = logging.getLogger(__name__)

# ─── Available Models (served to the UI dropdowns) ────────────────────

AVAILABLE_MODELS = [
    {"id": "gemini-3-pro-preview", "label": "Gemini 3 Pro (Preview)", "tier": "pro"},
    {"id": "gemini-3-flash-preview", "label": "Gemini 3 Flash (Preview)", "tier": "flash"},
    {"id": "gemini-2.5-pro", "label": "Gemini 2.5 Pro", "tier": "pro"},
    {"id": "gemini-2.5-flash", "label": "Gemini 2.5 Flash", "tier": "flash"},
]

IMAGE_MODELS = [
    {"id": "gemini-3-pro-image-preview", "label": "Gemini 3 Pro Image (Preview)"},
]


# ─── Default Model Constants (from env vars or hardcoded defaults) ────

MODEL_ROUTER = os.getenv("MODEL_ROUTER", "gemini-3-flash-preview")
MODEL_COMPANY_RESEARCH = os.getenv("MODEL_COMPANY_RESEARCH", "gemini-3-flash-preview")
MODEL_MARKET_ANALYSIS = os.getenv("MODEL_MARKET_ANALYSIS", "gemini-3-flash-preview")
MODEL_FACT_VERIFICATION = os.getenv("MODEL_FACT_VERIFICATION", "gemini-3-flash-preview")
MODEL_FINANCIAL_MODELING = os.getenv("MODEL_FINANCIAL_MODELING", "gemini-3-pro-preview")
MODEL_RISK_ASSESSMENT = os.getenv("MODEL_RISK_ASSESSMENT", "gemini-3-pro-preview")
MODEL_INVESTOR_MEMO = os.getenv("MODEL_INVESTOR_MEMO", "gemini-3-pro-preview")
MODEL_MEMO_QA = os.getenv("MODEL_MEMO_QA", "gemini-3-pro-preview")
MODEL_HTML_REPORT = os.getenv("MODEL_HTML_REPORT", "gemini-3-flash-preview")
MODEL_INFOGRAPHIC = os.getenv("MODEL_INFOGRAPHIC", "gemini-3-flash-preview")
MODEL_PDF_REPORT = os.getenv("MODEL_PDF_REPORT", "gemini-3-flash-preview")
MODEL_TOOLS_HTML_GENERATION = os.getenv("MODEL_TOOLS_HTML_GENERATION", "gemini-3-flash-preview")
MODEL_TOOLS_IMAGE_GENERATION = os.getenv("MODEL_TOOLS_IMAGE_GENERATION", "gemini-3-pro-image-preview")


# ─── Agent Model Registry ─────────────────────────────────────────────
# Maps config keys to their metadata. Agent references are registered
# at import time by agent.py via register_agents().

AGENT_MODEL_MAP = {
    "MODEL_ROUTER": {"label": "Router Agent", "default": MODEL_ROUTER},
    "MODEL_COMPANY_RESEARCH": {"label": "Company Research", "default": MODEL_COMPANY_RESEARCH},
    "MODEL_MARKET_ANALYSIS": {"label": "Market Analysis", "default": MODEL_MARKET_ANALYSIS},
    "MODEL_FACT_VERIFICATION": {"label": "Fact Verification (QA1)", "default": MODEL_FACT_VERIFICATION},
    "MODEL_FINANCIAL_MODELING": {"label": "Financial Modeling", "default": MODEL_FINANCIAL_MODELING},
    "MODEL_RISK_ASSESSMENT": {"label": "Risk Assessment", "default": MODEL_RISK_ASSESSMENT},
    "MODEL_INVESTOR_MEMO": {"label": "Investor Memo", "default": MODEL_INVESTOR_MEMO},
    "MODEL_MEMO_QA": {"label": "Memo QA (QA2)", "default": MODEL_MEMO_QA},
    "MODEL_HTML_REPORT": {"label": "HTML Report", "default": MODEL_HTML_REPORT},
    "MODEL_INFOGRAPHIC": {"label": "Infographic", "default": MODEL_INFOGRAPHIC},
    "MODEL_PDF_REPORT": {"label": "PDF Report", "default": MODEL_PDF_REPORT},
    "MODEL_TOOLS_HTML_GENERATION": {"label": "Tools: HTML Generation", "default": MODEL_TOOLS_HTML_GENERATION},
    "MODEL_TOOLS_IMAGE_GENERATION": {"label": "Tools: Image Generation", "default": MODEL_TOOLS_IMAGE_GENERATION},
}

# Runtime overrides (set by the web UI, stored in Redis, applied here)
_overrides = {}
_agent_refs = {}


def register_agents(agents: dict):
    """Register agent references for runtime model changes.

    Called by agent.py after all agents are defined.
    agents: {"MODEL_ROUTER": root_agent, "MODEL_COMPANY_RESEARCH": company_research_agent, ...}
    """
    _agent_refs.update(agents)


def apply_model_overrides(overrides: dict):
    """Apply model overrides to running agent instances.

    overrides: {"MODEL_COMPANY_RESEARCH": "gemini-2.5-flash", ...}
    Only keys present in AGENT_MODEL_MAP are applied. Unknown keys are ignored.
    """
    _overrides.clear()
    _overrides.update(overrides)

    for key, model_id in overrides.items():
        if key in _agent_refs and model_id:
            agent = _agent_refs[key]
            agent.model = model_id
            logger.info(f"Model override applied: {key} -> {model_id}")
        elif key.startswith("MODEL_TOOLS_"):
            # Tools overrides are stored in _overrides, read at call time
            logger.info(f"Tools model override stored: {key} -> {model_id}")


def reset_model_overrides():
    """Reset all agents to their default models (from env vars / hardcoded)."""
    for key, meta in AGENT_MODEL_MAP.items():
        if key in _agent_refs:
            _agent_refs[key].model = meta["default"]
            logger.info(f"Model reset: {key} -> {meta['default']}")
    _overrides.clear()


def get_tools_model(key: str) -> str:
    """Get the current model for a tools.py direct API call.

    Checks runtime overrides first, then falls back to the module constant.
    """
    if key in _overrides and _overrides[key]:
        return _overrides[key]
    return AGENT_MODEL_MAP.get(key, {}).get("default", "gemini-3-flash-preview")


def get_current_config() -> dict:
    """Return the full current configuration for the API/UI.

    Returns dict with agents list, available_models, and image_models.
    """
    agents = []
    for key, meta in AGENT_MODEL_MAP.items():
        current = _overrides.get(key)
        if not current and key in _agent_refs:
            current = _agent_refs[key].model if hasattr(_agent_refs[key], 'model') else meta["default"]
        elif not current:
            current = meta["default"]
        agents.append({
            "key": key,
            "label": meta["label"],
            "current_model": current,
            "default_model": meta["default"],
            "is_image_model": key == "MODEL_TOOLS_IMAGE_GENERATION",
        })
    return {
        "agents": agents,
        "available_models": AVAILABLE_MODELS,
        "image_models": IMAGE_MODELS,
    }


# ─── Redis-based Config Loading (called before each pipeline run) ─────

_redis_client = None

REDIS_HOST = os.getenv("REDIS_HOST", "redis-cluster.redis.svc.cluster.local")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_CONFIG_KEY = "model_config"


def _get_redis_client():
    """Lazy-initialize async Redis cluster client."""
    global _redis_client
    if _redis_client is None:
        import redis.asyncio.cluster as aioredis_cluster
        _redis_client = aioredis_cluster.RedisCluster(
            host=REDIS_HOST, port=REDIS_PORT, decode_responses=True
        )
    return _redis_client


async def load_and_apply_from_redis():
    """Load model overrides from Redis and apply to running agents.

    Called by root_agent's before_agent_callback on every pipeline invocation.
    If Redis is unavailable or has no overrides, agents keep their current models.
    """
    try:
        client = _get_redis_client()
        config_json = await client.get(REDIS_CONFIG_KEY)
        if config_json:
            overrides = json.loads(config_json)
            apply_model_overrides(overrides)
            logger.info(f"Applied {len(overrides)} model overrides from Redis")
        else:
            reset_model_overrides()
    except Exception as e:
        logger.warning(f"Could not load config from Redis (using current models): {e}")
