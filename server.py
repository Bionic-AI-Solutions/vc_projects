"""Helper module to get user email from Redis (per-session storage via kong-proxy)."""

import os
import logging
import redis.cluster as redis_cluster

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("UserEmailHelper")

# Redis cluster connection
REDIS_HOST = os.environ.get("REDIS_HOST", "redis-cluster.redis.svc.cluster.local")
REDIS_PORT = int(os.environ.get("REDIS_PORT", "6379"))

redis_client = redis_cluster.RedisCluster(
    host=REDIS_HOST, port=REDIS_PORT, decode_responses=True
)


def get_current_user_email(session_id: str = "") -> str:
    """Get the current user email from Redis, keyed by ADK session_id.

    The kong-proxy sidecar stores email->session_id mappings in Redis
    when it intercepts requests with Kong authentication headers.

    Args:
        session_id: The ADK session_id to look up the email for.

    Returns:
        User email from Redis, or empty string if not available.
    """
    if not session_id:
        logger.debug("No session_id provided, cannot look up email")
        return ""

    try:
        key = f"session_email:{session_id}"
        email = redis_client.get(key)
        if email:
            logger.info(f"Retrieved user email from Redis for session {session_id}: {email}")
            return email
    except Exception as e:
        logger.debug(f"Could not read user email from Redis: {e}")

    logger.debug(f"No user email available for session_id: {session_id}")
    return ""
