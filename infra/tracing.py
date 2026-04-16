"""LangSmith tracing setup."""

import logging
import os

logger = logging.getLogger(__name__)


def setup_tracing():
    """Configure LangSmith tracing from environment variables."""
    if os.environ.get("LANGCHAIN_TRACING_V2") == "true":
        api_key = os.environ.get("LANGCHAIN_API_KEY")
        if not api_key:
            logger.warning("LANGCHAIN_TRACING_V2 is true but LANGCHAIN_API_KEY is missing.")
            return

        project = os.environ.get("LANGCHAIN_PROJECT", "default")
        endpoint = os.environ.get("LANGCHAIN_ENDPOINT", "https://api.smith.langchain.com")
        logger.info(f"LangSmith tracing enabled for project: {project} at {endpoint}")
