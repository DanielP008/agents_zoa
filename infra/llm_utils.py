"""LLM utilities with safe error handling."""

import json
import logging
import time
from functools import wraps
from typing import Any, Callable, Dict, Optional, TypeVar

from infra.timing import Timer

logger = logging.getLogger(__name__)

T = TypeVar('T')


def _extract_model_from_chain(chain: Any) -> str:
    """Extract the model name from a LangChain chain (prompt | llm)."""
    for attr_name in ("last", "middle"):
        obj = getattr(chain, attr_name, None)
        if obj is None:
            continue
        if isinstance(obj, (list, tuple)):
            for item in obj:
                name = _get_model_name(item)
                if name:
                    return name
        else:
            name = _get_model_name(obj)
            if name:
                return name
    return ""


def _get_model_name(obj: Any) -> str:
    """Try multiple attributes to find a model name."""
    for attr in ("model_name", "model", "model_id"):
        val = getattr(obj, attr, None)
        if val and isinstance(val, str):
            return val
    inner = getattr(obj, "llm", None)
    if inner:
        for attr in ("model_name", "model", "model_id"):
            val = getattr(inner, attr, None)
            if val and isinstance(val, str):
                return val
    return ""


def _is_empty_response(obj: Any) -> bool:
    """Check if a structured response object is essentially empty."""
    if obj is None:
        return True

    if hasattr(obj, '__dict__'):
        attrs = obj.__dict__
    elif hasattr(obj, 'dict') and callable(obj.dict):
        attrs = obj.dict()
    else:
        return False

    has_content = False
    for key, value in attrs.items():
        if key.startswith('_'):
            continue
        if isinstance(value, str) and value.strip():
            has_content = True
            break
        elif isinstance(value, (list, tuple)) and len(value) > 0:
            has_content = True
            break
        elif isinstance(value, dict) and len(value) > 0:
            has_content = True
            break
        elif isinstance(value, (int, float)) and value != 0:
            has_content = True
            break

    return not has_content


def safe_structured_invoke(
    chain: Any,
    inputs: Dict[str, Any],
    fallback_factory: Callable[[], T],
    error_context: Optional[str] = None,
    max_retries: int = 3
) -> T:
    """Safely invoke a structured output chain with retry on empty responses."""
    context_msg = f" [{error_context}]" if error_context else ""
    agent_label = error_context or "unknown_classifier"

    for attempt in range(max_retries):
        try:
            model_name_str = _extract_model_from_chain(chain)

            with Timer("agent", agent_label, model=model_name_str):
                result = chain.invoke(inputs)

            if result is None:
                logger.warning(f"Structured output returned None{context_msg} (attempt {attempt + 1}/{max_retries})")
                if attempt < max_retries - 1:
                    continue
                return fallback_factory()

            if _is_empty_response(result):
                logger.warning(f"Structured output returned empty response{context_msg} (attempt {attempt + 1}/{max_retries})")
                if attempt < max_retries - 1:
                    continue
                return fallback_factory()

            return result
        except Exception as e:
            logger.error(f"Structured output error{context_msg} (attempt {attempt + 1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                continue
            return fallback_factory()

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
