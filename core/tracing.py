import os
import logging

logger = logging.getLogger(__name__)

def setup_tracing():
    """
    Configures LangSmith tracing based on environment variables.
    This should be called at application startup.
    """
    if os.environ.get("LANGCHAIN_TRACING_V2") == "true":
        api_key = os.environ.get("LANGCHAIN_API_KEY")
        if not api_key:
            logger.warning("LANGCHAIN_TRACING_V2 is true but LANGCHAIN_API_KEY is missing.")
            return

        project = os.environ.get("LANGCHAIN_PROJECT", "default")
        endpoint = os.environ.get("LANGCHAIN_ENDPOINT", "https://api.smith.langchain.com")
        logger.info(f"LangSmith tracing enabled for project: {project} at {endpoint}")
