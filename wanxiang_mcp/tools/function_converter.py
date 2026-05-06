"""Convert MCP tool schemas to OpenAI function calling format."""

from __future__ import annotations

from typing import Any, Dict, List, Type

from pydantic import BaseModel


def pydantic_to_openai_parameters(model: Type[BaseModel]) -> Dict[str, Any]:
    """Convert a pydantic model to OpenAI function parameters format."""
    schema = model.model_json_schema()

    properties: Dict[str, Any] = {}
    required: List[str] = []

    for name, prop in schema.get("properties", {}).items():
        # Skip internal fields
        if name.startswith("_"):
            continue

        prop_copy = dict(prop)

        # Map pydantic types to JSON Schema types
        # Handle Optional types - they have "anyOf" with null
        if "anyOf" in prop_copy:
            types = [t for t in prop_copy["anyOf"] if t.get("type") != "null"]
            if len(types) == 1:
                prop_copy = types[0]
            else:
                # Multiple types
                prop_copy = {"type": "string"}

        json_type = prop_copy.get("type", "string")
        # Map to OpenAI compatible types
        if json_type == "float":
            prop_copy["type"] = "number"
        elif json_type == "integer":
            prop_copy["type"] = "integer"

        # Remove descriptions for now if they contain markdown
        # Keep title as description
        if "title" in prop_copy and "description" not in prop_copy:
            prop_copy["description"] = prop_copy.pop("title")

        properties[name] = prop_copy

    # Required fields are those without default values
    required = schema.get("required", [])

    return {
        "type": "object",
        "properties": properties,
        "required": required,
    }


def mcp_tool_to_openai_function(
    name: str,
    description: str,
    input_model: Type[BaseModel],
) -> Dict[str, Any]:
    """Convert an MCP tool to OpenAI function format."""
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": pydantic_to_openai_parameters(input_model),
        },
    }


def list_openai_functions() -> List[Dict[str, Any]]:
    """Get all MCP tools converted to OpenAI function format."""
    from wanxiang_mcp.tools.chat_session import CHAT_SESSION_TOOLS
    from wanxiang_mcp.tools.report import REPORT_TOOLS

    functions = []
    for tool in CHAT_SESSION_TOOLS + REPORT_TOOLS:
        functions.append(
            mcp_tool_to_openai_function(
                name=tool.name,
                description=tool.description,
                input_model=tool.input_model,
            )
        )
    return functions
