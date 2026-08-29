"""Provider-neutral manual tool-use loop for the refund agent."""
from __future__ import annotations

from typing import Any, Mapping, Sequence

from ..config import AGENT_LIMITS, AgentLimits
from ..ids import idempotency_key as make_idempotency_key
from ..ids import intent_id as make_intent_id
from ..ids import tool_call_id as make_tool_call_id
from ..schemas import AgentTrace
from .interfaces import (
    AgentTool,
    ModelClient,
    ToolCall,
    ToolContext,
    ToolExecution,
    UserRequest,
)
from .prompts import DEFAULT_REFUND_SYSTEM_PROMPT
from .recorder import AgentRecorder

_CORRELATION_ARGUMENTS = {"intent_id", "idempotency_key", "tool_call_id"}


class RefundAgent:
    """Run model turns and tools while recording exactly what each side saw."""

    def __init__(
        self,
        model_client: ModelClient,
        tools: Sequence[AgentTool],
        *,
        system_prompt: str = DEFAULT_REFUND_SYSTEM_PROMPT,
        limits: AgentLimits = AGENT_LIMITS,
    ):
        self.model_client = model_client
        self.system_prompt = system_prompt
        self.limits = limits
        self._tools: dict[str, AgentTool] = {}
        for tool in tools:
            name = tool.spec.name
            if name in self._tools:
                raise ValueError(f"duplicate tool name {name!r}")
            self._tools[name] = tool

    @property
    def tool_specs(self):
        return tuple(tool.spec for tool in self._tools.values())

    def run_request(
        self,
        *,
        case_id: str,
        text: str,
        intent_id: str | None = None,
    ) -> AgentTrace:
        """Run one user request and return its complete :class:`AgentTrace`."""
        request = UserRequest(intent_id or make_intent_id(case_id, 0), text)
        return self.run(case_id=case_id, user_requests=(request,))

    def run(
        self,
        *,
        case_id: str,
        user_requests: Sequence[UserRequest | Mapping[str, str]],
    ) -> AgentTrace:
        requests = tuple(self._coerce_request(r) for r in user_requests)
        if not requests:
            raise ValueError("at least one user request is required")

        recorder = AgentRecorder(
            case_id=case_id,
            model_name=self.model_client.model_name,
            system_prompt=self.system_prompt,
        )
        reports: list[str] = []
        attempt_ordinal = 0
        final_stop_reason: str | None = None

        for request in requests:
            recorder.record_user(request)
            for _turn in range(self.limits.max_turns):
                response = self.model_client.complete(
                    messages=recorder.model_messages(),
                    tools=self.tool_specs,
                    max_output_tokens=self.limits.max_output_tokens,
                    effort=self.limits.effort,
                )

                assigned: list[tuple[str, ToolCall, dict[str, Any]]] = []
                contexts: list[ToolContext] = []
                for call in response.tool_calls:
                    call_id = make_tool_call_id(case_id, attempt_ordinal)
                    arguments, context = self._invocation(
                        case_id=case_id,
                        request=request,
                        call=call,
                        tool_call_id=call_id,
                        attempt_ordinal=attempt_ordinal,
                    )
                    attempt_ordinal += 1
                    assigned.append((call_id, call, arguments))
                    contexts.append(context)

                recorder.record_assistant(response, assigned)
                if not assigned:
                    reports.append(response.text.strip())
                    final_stop_reason = response.stop_reason or "end_turn"
                    break

                for (call_id, call, arguments), context in zip(assigned, contexts):
                    execution = self._execute(call.name, arguments, context)
                    recorder.record_tool(
                        tool_call_id=call_id,
                        intent_id=request.intent_id,
                        tool_name=call.name,
                        arguments=arguments,
                        execution=execution,
                    )
            else:
                return recorder.finish(
                    final_report="\n\n".join(r for r in reports if r),
                    stop_reason="max_turns",
                )

        return recorder.finish(
            final_report="\n\n".join(r for r in reports if r),
            stop_reason=final_stop_reason,
        )

    @staticmethod
    def _coerce_request(request: UserRequest | Mapping[str, str]) -> UserRequest:
        if isinstance(request, UserRequest):
            return request
        return UserRequest(intent_id=request["intent_id"], text=request["text"])

    @staticmethod
    def _invocation(
        *,
        case_id: str,
        request: UserRequest,
        call: ToolCall,
        tool_call_id: str,
        attempt_ordinal: int,
    ) -> tuple[dict[str, Any], ToolContext]:
        business_args = {
            key: value
            for key, value in call.arguments.items()
            if key not in _CORRELATION_ARGUMENTS
        }
        idem = make_idempotency_key(request.intent_id, call.name, business_args)
        arguments = {
            **business_args,
            "intent_id": request.intent_id,
            "idempotency_key": idem,
            "tool_call_id": tool_call_id,
        }
        context = ToolContext(
            case_id=case_id,
            intent_id=request.intent_id,
            tool_call_id=tool_call_id,
            idempotency_key=idem,
            attempt_ordinal=attempt_ordinal,
        )
        return arguments, context

    def _execute(
        self,
        tool_name: str,
        arguments: Mapping[str, Any],
        context: ToolContext,
    ) -> ToolExecution:
        tool = self._tools.get(tool_name)
        if tool is None:
            return ToolExecution.failure(f"UnknownTool: {tool_name}")
        try:
            raw = tool.execute(arguments, context)
            if isinstance(raw, ToolExecution):
                return raw
            if isinstance(raw, Mapping):
                return ToolExecution.success(raw)
            return ToolExecution.failure(
                f"InvalidToolResult: {tool_name} returned {type(raw).__name__}"
            )
        except Exception as exc:  # a tool failure is model input, not a runner crash
            return ToolExecution.failure(
                f"{type(exc).__name__}: {exc}",
                started_seq=getattr(exc, "started_seq", None),
                ended_seq=getattr(exc, "ended_seq", None),
            )
