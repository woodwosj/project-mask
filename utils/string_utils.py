"""String utility functions for PROJECT MASK.

This module provides helper functions for string manipulation
used throughout the codebase.
"""

from typing import List, Optional


def truncate(text: str, max_length: int, suffix: str = "...") -> str:
    """Truncate a string to a maximum length.

    Args:
        text: The string to truncate.
        max_length: Maximum length including suffix.
        suffix: String to append when truncated.

    Returns:
        Truncated string with suffix if needed.
    """
    if len(text) <= max_length:
        return text
    return text[:max_length - len(suffix)] + suffix


def word_wrap(text: str, width: int = 80) -> List[str]:
    """Wrap text to a specified width.

    Args:
        text: The text to wrap.
        width: Maximum line width.

    Returns:
        List of wrapped lines.
    """
    words = text.split()
    lines = []
    current_line = []
    current_length = 0

    for word in words:
        if current_length + len(word) + len(current_line) > width:
            lines.append(" ".join(current_line))
            current_line = [word]
            current_length = len(word)
        else:
            current_line.append(word)
            current_length += len(word)

    if current_line:
        lines.append(" ".join(current_line))

    return lines


def snake_to_camel(text: str) -> str:
    """Convert snake_case to camelCase.

    Args:
        text: Snake case string.

    Returns:
        Camel case string.
    """
    components = text.split("_")
    return components[0] + "".join(x.title() for x in components[1:])


def camel_to_snake(text: str) -> str:
    """Convert camelCase to snake_case.

    Args:
        text: Camel case string.

    Returns:
        Snake case string.
    """
    result = []
    for char in text:
        if char.isupper() and result:
            result.append("_")
        result.append(char.lower())
    return "".join(result)
