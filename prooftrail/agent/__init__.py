"""Provider-neutral refund agent, live providers and offline replay support."""

from .adapters import DispatchToolSuite, ToolSuiteAction
from .anthropic_client import (
    API_KEY_ENV,
    AnthropicModelClient,
    MissingApiKeyError,
    ProviderTransientError,
)
from .budget import BUDGET_ENV, BudgetExceededError, BudgetGuard, CostLedger
from .cache import CachingModelClient, ReplayCache, ReplayCacheMiss, ReplayCacheModelMismatch
from .gemini_client import (
    DEFAULT_GEMINI_MODEL,
    FREE_TIER_MODELS,
    GEMINI_API_KEY_ENV,
    GEMINI_FREE_TIER_ENV,
    FreeTierConfirmationError,
    GeminiModelClient,
    GeminiResponseError,
    GeminiTransportError,
    MissingGeminiApiKeyError,
)
from .interfaces import (
    AgentTool,
    ModelClient,
    ModelResponse,
    ToolCall,
    ToolContext,
    ToolExecution,
    ToolSpec,
    UserRequest,
    prompt_sha256,
)
from .refund_agent import RefundAgent
from .replay import (
    load_agent_trace,
    load_scripted_responses,
    save_agent_trace,
    save_scripted_responses,
)
from .scripted import ScriptExhaustedError, ScriptedModelClient
from .tool_defs import REFUND_TOOL_SPECS, build_refund_tool_actions

__all__ = [
    "API_KEY_ENV",
    "AgentTool",
    "AnthropicModelClient",
    "BUDGET_ENV",
    "BudgetExceededError",
    "BudgetGuard",
    "CachingModelClient",
    "CostLedger",
    "DispatchToolSuite",
    "DEFAULT_GEMINI_MODEL",
    "FREE_TIER_MODELS",
    "FreeTierConfirmationError",
    "GEMINI_API_KEY_ENV",
    "GEMINI_FREE_TIER_ENV",
    "GeminiModelClient",
    "GeminiResponseError",
    "GeminiTransportError",
    "MissingApiKeyError",
    "MissingGeminiApiKeyError",
    "ModelClient",
    "ModelResponse",
    "ProviderTransientError",
    "RefundAgent",
    "REFUND_TOOL_SPECS",
    "ReplayCache",
    "ReplayCacheMiss",
    "ReplayCacheModelMismatch",
    "ScriptExhaustedError",
    "ScriptedModelClient",
    "ToolCall",
    "ToolContext",
    "ToolExecution",
    "ToolSpec",
    "ToolSuiteAction",
    "UserRequest",
    "build_refund_tool_actions",
    "load_agent_trace",
    "load_scripted_responses",
    "prompt_sha256",
    "save_agent_trace",
    "save_scripted_responses",
]
