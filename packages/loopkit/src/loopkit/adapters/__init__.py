from loopkit.adapters.base import ModelAdapter, ModelResult, ToolCall
from loopkit.adapters.mock import MockAdapter, act, final
from loopkit.adapters.ollama import OllamaAdapter, OllamaError
from loopkit.adapters.openai_compat import (
    OpenAICompatError,
    OpenAICompatibleAdapter,
    parse_openai_message,
    tool_specs,
)
from loopkit.adapters.react import (
    ReActAdapter,
    TextCompletion,
    parse_react_response,
    react_preamble,
)

__all__ = [
    "ModelAdapter",
    "ModelResult",
    "ToolCall",
    "MockAdapter",
    "act",
    "final",
    # react
    "ReActAdapter",
    "TextCompletion",
    "parse_react_response",
    "react_preamble",
    # ollama
    "OllamaAdapter",
    "OllamaError",
    # openai-compatible
    "OpenAICompatibleAdapter",
    "OpenAICompatError",
    "parse_openai_message",
    "tool_specs",
]
