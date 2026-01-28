"""LLM utilities with safe error handling."""
import logging
from typing import Any, Dict, Optional, Callable, TypeVar, Type

logger = logging.getLogger(__name__)

T = TypeVar('T')


def safe_structured_invoke(
    chain: Any,
    inputs: Dict[str, Any],
    fallback_factory: Callable[[], T],
    error_context: Optional[str] = None
) -> T:
    """Safely invoke a structured output chain."""
    context_msg = f" [{error_context}]" if error_context else ""
    
    print(f"\n[SAFE_INVOKE DEBUG]{context_msg} Starting chain invocation...")
    print(f"[SAFE_INVOKE DEBUG]{context_msg} Inputs: {inputs}")
    
    try:
        result = chain.invoke(inputs)
        
        print(f"[SAFE_INVOKE DEBUG]{context_msg} Raw result: {result}")
        print(f"[SAFE_INVOKE DEBUG]{context_msg} Result type: {type(result)}")
        print(f"[SAFE_INVOKE DEBUG]{context_msg} Result is None: {result is None}")
        
        if result is None:
            print(f"[SAFE_INVOKE DEBUG]{context_msg} Result is None, using fallback")
            logger.warning(f"Structured output returned None{context_msg}, using fallback")
            return fallback_factory()
        
        print(f"[SAFE_INVOKE DEBUG]{context_msg} Returning valid result")
        return result
    except Exception as e:
        print(f"[SAFE_INVOKE DEBUG]{context_msg} Exception caught: {type(e).__name__}: {e}")
        logger.error(f"Structured output error{context_msg}: {e}")
        return fallback_factory()


def safe_llm_invoke(
    chain_callable: Callable,
    inputs: Dict[str, Any],
    fallback: Optional[Any] = None,
    log_error: bool = True,
    error_context: Optional[str] = None
) -> Any:
    """Safely invoke an LLM callable with error handling."""
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
    """Parse an LLM JSON response with cleanup and validation."""
    if not raw_response:
        return fallback or {}

    if hasattr(raw_response, 'content'):
        content = raw_response.content
    else:
        content = str(raw_response)

    content = content.strip()
    if content.startswith("```"):
        lines = content.split("\n")
        if len(lines) > 2 and lines[0].startswith("```"):
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
    """Create a retry decorator for LLM operations."""
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

            return {"error": f"Operation failed after {max_retries + 1} attempts", "last_exception": str(last_exception)}

        return wrapper
    return decorator