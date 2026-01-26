"""
LLM utilities with safe error handling and consistent behavior.
"""
import logging
from typing import Any, Dict, Optional, Callable

logger = logging.getLogger(__name__)


def safe_llm_invoke(
    chain_callable: Callable,
    inputs: Dict[str, Any],
    fallback: Optional[Any] = None,
    log_error: bool = True,
    error_context: Optional[str] = None
) -> Any:
    """
    Safely invoke LLM chains with error handling and logging.

    Args:
        chain_callable: Function/callable to invoke (chain.invoke, etc.)
        inputs: Input dictionary for the chain
        fallback: Value to return on error (default: None)
        log_error: Whether to log errors (default: True)
        error_context: Additional context for error logging

    Returns:
        Chain result or fallback value on error
    """
    try:
        return chain_callable(inputs)
    except Exception as e:
        context_msg = f" [{error_context}]" if error_context else ""
        if log_error:
            logger.error(f"LLM Error{context_msg}: {e}")
            logger.debug(f"LLM Input{context_msg}: {inputs}")
        return fallback


def parse_llm_json_response(
    raw_response: Any,
    expected_keys: Optional[list] = None,
    fallback: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Parse LLM JSON responses with cleanup and validation.

    Args:
        raw_response: Raw response from LLM
        expected_keys: Keys that should be present in response
        fallback: Fallback dict if parsing fails

    Returns:
        Parsed and cleaned response dict
    """
    if not raw_response:
        return fallback or {}

    # Extract content if it's a LangChain response object
    if hasattr(raw_response, 'content'):
        content = raw_response.content
    else:
        content = str(raw_response)

    # Clean markdown formatting
    content = content.strip()
    if content.startswith("```"):
        # Remove markdown code blocks
        lines = content.split("\n")
        if len(lines) > 2 and lines[0].startswith("```"):
            # Remove opening ``` and optional language marker
            content = "\n".join(lines[1:])
            if "```" in content:
                content = content.split("```")[0]

    content = content.strip()
    if content.startswith("```json"):
        content = content[7:]
    if content.startswith("json"):
        content = content[4:]

    content = content.strip()

    try:
        import json
        parsed = json.loads(content)

        # Basic validation if expected keys provided
        if expected_keys and isinstance(parsed, dict):
            missing_keys = [key for key in expected_keys if key not in parsed]
            if missing_keys:
                logger.warning(f"LLM response missing expected keys: {missing_keys}")
                if fallback:
                    return fallback

        return parsed

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse LLM JSON response: {e}")
        logger.debug(f"Raw content: {content[:200]}...")
        return fallback or {}


def create_llm_retry_decorator(
    max_retries: int = 3,
    backoff_factor: float = 1.0,
    exceptions: tuple = (Exception,)
):
    """
    Create a retry decorator for LLM operations.

    Args:
        max_retries: Maximum number of retry attempts
        backoff_factor: Backoff multiplier for sleep time
        exceptions: Tuple of exceptions to catch and retry

    Returns:
        Decorator function
    """
    import time
    from functools import wraps

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt < max_retries:
                        sleep_time = backoff_factor * (2 ** attempt)
                        logger.warning(f"LLM operation failed (attempt {attempt + 1}/{max_retries + 1}), retrying in {sleep_time}s: {e}")
                        time.sleep(sleep_time)
                    else:
                        logger.error(f"LLM operation failed after {max_retries + 1} attempts: {e}")

            # If all retries failed, return a safe fallback
            return {"error": f"Operation failed after {max_retries + 1} attempts", "last_exception": str(last_exception)}

        return wrapper
    return decorator