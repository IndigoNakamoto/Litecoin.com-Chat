"""
Input sanitization utilities for preventing injection attacks and enforcing length limits.
"""

import re
import logging
from typing import Tuple, Optional

logger = logging.getLogger(__name__)

# Maximum length for chat queries and search inputs
# Increased from 400 to 2000 to accommodate longer chat history messages
# Individual messages can be long, and we need room for context
MAX_QUERY_LENGTH = 2000

# Prompt injection patterns to detect and neutralize
PROMPT_INJECTION_PATTERNS = [
    r'(?i)ignore\s+(?:(?:all|any|the)\s+)?(previous|prior|above|earlier|all)\s+(instructions?|prompts?|rules?)',
    r'(?i)forget\s+(everything|all|previous)',
    r'(?i)new\s+instructions?',
    r'(?i)system\s*:',
    r'(?i)you\s+are\s+now',
    r'(?i)act\s+as\s+if',
    r'(?i)pretend\s+to\s+be',
    r'(?i)disregard\s+(previous|all|above)',
    r'(?i)override\s+(previous|all|above)',
    r'(?i)bypass\s+(previous|all|above)',
    r'(?i)jailbreak',
    r'(?i)roleplay',
    r'(?i)you\s+must\s+(ignore|forget|disregard)',
]

# MongoDB NoSQL injection dangerous characters and operators
NOSQL_DANGEROUS_CHARS = ['$', '.', '\x00']
NOSQL_OPERATORS = ['$where', '$ne', '$gt', '$lt', '$gte', '$lte', '$in', '$nin', '$regex']


def detect_prompt_injection(text: str) -> Tuple[bool, Optional[str]]:
    """
    Detect potential prompt injection attempts in text.
    
    Args:
        text: The text to check for prompt injection patterns.
        
    Returns:
        Tuple of (is_injection, matched_pattern) where is_injection is True if
        a pattern was detected, and matched_pattern is the pattern that matched.
    """
    if not text:
        return False, None
    
    text_lower = text.lower()
    for pattern in PROMPT_INJECTION_PATTERNS:
        if re.search(pattern, text):
            # Log pattern detected but don't expose full user input
            logger.warning(f"Prompt injection pattern detected: {pattern} (input length: {len(text)} chars)")
            return True, pattern
    
    return False, None


def sanitize_prompt_injection(text: str) -> str:
    """
    Sanitize text by neutralizing prompt injection attempts.
    Escapes detected patterns by wrapping them in quotes or removing them.
    
    Args:
        text: The text to sanitize.
        
    Returns:
        Sanitized text with prompt injection patterns neutralized.
    """
    if not text:
        return text
    
    is_injection, pattern = detect_prompt_injection(text)
    if is_injection:
        # Neutralize by escaping the pattern - wrap suspicious phrases
        # This preserves the text but makes it less likely to be interpreted as instructions
        sanitized = re.sub(
            pattern,
            lambda m: f'[user input: {m.group(0)}]',
            text,
            flags=re.IGNORECASE
        )
        logger.info(f"Sanitized prompt injection attempt. Pattern: {pattern}")
        return sanitized
    
    return text


def sanitize_nosql_injection(text: str) -> str:
    """
    Sanitize text to prevent NoSQL injection attacks.
    Escapes or removes dangerous MongoDB operators and characters.
    
    Args:
        text: The text to sanitize.
        
    Returns:
        Sanitized text safe for MongoDB queries.
    """
    if not text:
        return text
    
    sanitized = text
    
    # Remove null bytes
    sanitized = sanitized.replace('\x00', '')
    
    # Escape MongoDB operators if they appear at the start of words
    # This prevents injection while preserving legitimate use in text
    for operator in NOSQL_OPERATORS:
        # Only escape if it looks like an operator (preceded by whitespace or start of string)
        pattern = r'(^|\s)(' + re.escape(operator) + r')(\s|$)'
        if re.search(pattern, sanitized, re.IGNORECASE):
            # Replace with escaped version
            sanitized = re.sub(pattern, r'\1\\' + operator + r'\3', sanitized, flags=re.IGNORECASE)
            logger.warning(f"Escaped potential NoSQL operator: {operator}")
    
    # Escape dollar signs that might be used for MongoDB operators
    # But allow legitimate dollar signs in text (like "$100")
    # Only escape if it's followed by a letter (potential operator)
    sanitized = re.sub(r'\$([a-zA-Z])', r'\\$\1', sanitized)
    
    return sanitized


def validate_length(text: str, max_length: int = MAX_QUERY_LENGTH) -> Tuple[bool, Optional[str]]:
    """
    Validate that text does not exceed maximum length.
    
    Args:
        text: The text to validate.
        max_length: Maximum allowed length (default: MAX_QUERY_LENGTH).
        
    Returns:
        Tuple of (is_valid, error_message) where is_valid is True if length is OK.
    """
    if not text:
        return True, None
    
    if len(text) > max_length:
        error_msg = f"Input exceeds maximum length of {max_length} characters (got {len(text)})"
        logger.warning(error_msg)
        return False, error_msg
    
    return True, None


def sanitize_string(text: str, max_length: int = MAX_QUERY_LENGTH) -> str:
    """
    Sanitize string by removing null bytes and control characters.
    
    Args:
        text: The text to sanitize.
        max_length: Maximum allowed length.
        
    Returns:
        Sanitized text.
    """
    if not text:
        return text
    
    # Remove null bytes
    sanitized = text.replace('\x00', '')
    
    # Remove other control characters except newlines, tabs, and carriage returns
    sanitized = re.sub(r'[\x00-\x08\x0B-\x0C\x0E-\x1F\x7F]', '', sanitized)
    
    # Truncate if too long
    if len(sanitized) > max_length:
        sanitized = sanitized[:max_length]
        logger.warning(f"Input truncated to {max_length} characters")
    
    return sanitized


def sanitize_query_input(text: str, max_length: int = MAX_QUERY_LENGTH) -> str:
    """
    Comprehensive sanitization for user query inputs.
    Applies all sanitization steps: prompt injection, NoSQL injection, length validation.
    
    Args:
        text: The query text to sanitize.
        max_length: Maximum allowed length.
        
    Returns:
        Fully sanitized text safe for processing.
    """
    if not text:
        return text
    
    # First, validate length
    is_valid, error = validate_length(text, max_length)
    if not is_valid:
        # Truncate if too long
        text = text[:max_length]
    
    # Apply basic string sanitization
    sanitized = sanitize_string(text, max_length)
    
    # Apply prompt injection sanitization
    sanitized = sanitize_prompt_injection(sanitized)
    
    # Apply NoSQL injection sanitization
    sanitized = sanitize_nosql_injection(sanitized)
    
    return sanitized


def sanitize_mongodb_query_param(value: str) -> str:
    """
    Sanitize a value that will be used directly in a MongoDB query filter.
    This is more strict than general text sanitization.
    
    Args:
        value: The value to sanitize for MongoDB query use.
        
    Returns:
        Sanitized value safe for MongoDB queries.
    """
    if not value:
        return value
    
    # Remove null bytes
    sanitized = value.replace('\x00', '')
    
    # Remove MongoDB operators - for query params, we want to be strict
    # Only allow alphanumeric, spaces, hyphens, underscores for endpoint_type, etc.
    sanitized = re.sub(r'[^a-zA-Z0-9\s\-_]', '', sanitized)
    
    return sanitized.strip()

