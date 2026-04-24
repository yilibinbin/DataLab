#!/usr/bin/env python3
"""
Web interface helper for formula help and method descriptions.
Imports from the shared formula_help module to ensure consistency.
"""

import sys
from pathlib import Path

# Add parent directory to path to import formula_help
parent_dir = Path(__file__).parent.parent
if str(parent_dir) not in sys.path:
    sys.path.insert(0, str(parent_dir))

from formula_help import (
    get_function_help,
    get_function_tooltip,
    get_method_description,
    get_method_name,
    get_method_parameters,
    EXTRAPOLATION_METHODS,
    FUNCTION_HELP_ZH,
    FUNCTION_HELP_EN,
)


def get_function_help_html(lang: str = "zh") -> str:
    """Get function help text formatted as HTML for web display."""
    text = get_function_help(lang)
    # Convert plain text to HTML with proper formatting
    lines = text.split("\n")
    html_lines = []
    for line in lines:
        if not line.strip():
            html_lines.append("<br>")
        elif line.strip().endswith("：") or line.strip().endswith(":"):
            # Section headers
            html_lines.append(f"<h4>{line.strip()}</h4>")
        elif line.strip().startswith("•"):
            # Bullet points
            html_lines.append(f"<li>{line.strip()[1:].strip()}</li>")
        else:
            html_lines.append(f"<p>{line.strip()}</p>")
    return "\n".join(html_lines)


def get_method_help_html(method_key: str, lang: str = "zh") -> str:
    """Get method description formatted as HTML for web display."""
    description = get_method_description(method_key, lang)
    if not description:
        return ""

    # Convert plain text to HTML with proper formatting
    lines = description.split("\n")
    html_lines = []
    in_list = False

    for line in lines:
        stripped = line.strip()
        if not stripped:
            if in_list:
                html_lines.append("</ul>")
                in_list = False
            html_lines.append("<br>")
        elif stripped.endswith("：") or stripped.endswith(":"):
            if in_list:
                html_lines.append("</ul>")
                in_list = False
            html_lines.append(f"<h4>{stripped}</h4>")
        elif stripped.startswith("•"):
            if not in_list:
                html_lines.append("<ul>")
                in_list = True
            html_lines.append(f"<li>{stripped[1:].strip()}</li>")
        else:
            if in_list:
                html_lines.append("</ul>")
                in_list = False
            html_lines.append(f"<p>{stripped}</p>")

    if in_list:
        html_lines.append("</ul>")

    return "\n".join(html_lines)


# Export all functions from formula_help for convenience
__all__ = [
    "get_function_help",
    "get_function_tooltip",
    "get_method_description",
    "get_method_name",
    "get_method_parameters",
    "get_function_help_html",
    "get_method_help_html",
    "EXTRAPOLATION_METHODS",
]
