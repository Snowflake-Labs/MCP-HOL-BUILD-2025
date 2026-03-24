import json
import logging
import re
from typing import Any, Union, Iterator
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import BaseMessage, AIMessage, SystemMessage, HumanMessage, ToolMessage
from langchain_core.messages.tool import ToolCall
from langchain_core.outputs import ChatResult, ChatGeneration
from langchain_core.messages.ai import UsageMetadata

logger = logging.getLogger(__name__)


def _run_cortex_sql(session, model, messages_json, options_json):
    escaped_messages = messages_json.replace("\\", "\\\\").replace("'", "\\'")
    escaped_options = options_json.replace("\\", "\\\\").replace("'", "\\'")
    sql = (
        f"SELECT TO_VARCHAR(SNOWFLAKE.CORTEX.COMPLETE('{model}', "
        f"PARSE_JSON('{escaped_messages}'), "
        f"PARSE_JSON('{escaped_options}'))) AS result"
    )
    rows = session.sql(sql).collect()
    raw = rows[0]["RESULT"]
    if isinstance(raw, str):
        return json.loads(raw)
    if isinstance(raw, dict):
        return raw
    return json.loads(str(raw))


def patch_cortex_complete():
    import snowflake.cortex
    import snowflake.cortex._complete as _cm
    from snowflake.snowpark import Session as SnowparkSession
    import snowflake.snowpark as snowpark

    _original_complete = _cm.complete

    def _sql_complete(
        model,
        prompt,
        *,
        options=None,
        session=None,
        stream=False,
        timeout=None,
        deadline=None,
        **extra_kwargs,
    ):
        if isinstance(prompt, snowpark.Column) or isinstance(model, snowpark.Column):
            return _original_complete(
                model, prompt, options=options, session=session,
                stream=stream, timeout=timeout, deadline=deadline,
            )

        if session is None:
            try:
                from snowflake.snowpark import context
                session = context.get_active_session()
            except Exception:
                return _original_complete(
                    model, prompt, options=options, session=session,
                    stream=stream, timeout=timeout, deadline=deadline,
                )

        if isinstance(prompt, str):
            messages = [{"role": "user", "content": prompt}]
        elif isinstance(prompt, list):
            messages = prompt
        else:
            return _original_complete(
                model, prompt, options=options, session=session,
                stream=stream, timeout=timeout, deadline=deadline,
            )

        opts = {}
        if options is not None:
            if hasattr(options, 'items'):
                opts = dict(options)
            else:
                for key in ('temperature', 'max_tokens', 'top_p', 'guardrails', 'response_format'):
                    if hasattr(options, key):
                        val = getattr(options, key)
                        if val is not None:
                            opts[key] = val

        messages_json = json.dumps(messages)
        options_json = json.dumps(opts) if opts else '{}'

        result = _run_cortex_sql(session, model, messages_json, options_json)

        usage = result.get("usage", {})

        if "structured_output" in result:
            content = json.dumps(result["structured_output"][0]["raw_message"])
        else:
            content = result["choices"][0]["messages"]

        _last_usage[0] = {
            "model": result.get("model", model),
            "prompt_tokens": usage.get("prompt_tokens", 0),
            "completion_tokens": usage.get("completion_tokens", 0),
            "total_tokens": usage.get("total_tokens", 0),
            "guardrails_tokens": usage.get("guardrails_tokens", 0),
        }

        return content

    _last_usage = [{}]

    def get_last_usage():
        return _last_usage[0]

    _sql_complete.get_last_usage = get_last_usage
    _cm.complete = _sql_complete
    _cm._complete_impl = lambda *a, **kw: _sql_complete(*a, **kw)
    snowflake.cortex.complete = _sql_complete
    snowflake.cortex.Complete = _sql_complete


class ChatCortexSQL(BaseChatModel):
    session: Any
    model_name: str = "claude-3-5-sonnet"
    temperature: float = 0.1
    max_tokens: int = 4096
    _tools: list = []

    class Config:
        arbitrary_types_allowed = True

    @property
    def _llm_type(self) -> str:
        return "cortex-sql"

    def bind_tools(self, tools, **kwargs):
        clone = ChatCortexSQL(
            session=self.session,
            model_name=self.model_name,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        )
        clone._tools = tools
        return clone

    def _build_tool_schema(self):
        schemas = []
        for tool in self._tools:
            if hasattr(tool, "args_schema") and tool.args_schema:
                params = (
                    tool.args_schema.schema()
                    if hasattr(tool.args_schema, "schema")
                    else tool.args_schema
                )
            else:
                params = {"type": "object", "properties": {}}
            if "properties" in params:
                allowed = {"query"}
                params = dict(params)
                params["properties"] = {
                    k: v for k, v in params["properties"].items()
                    if k in allowed
                }
                if "required" in params:
                    params["required"] = [
                        r for r in params["required"] if r in allowed
                    ]
            schemas.append(
                {"name": tool.name, "description": tool.description, "parameters": params}
            )
        return schemas

    def _format_messages(self, messages):
        formatted = []
        for msg in messages:
            if isinstance(msg, SystemMessage):
                formatted.append({"role": "system", "content": msg.content})
            elif isinstance(msg, HumanMessage):
                formatted.append({"role": "user", "content": msg.content})
            elif isinstance(msg, AIMessage):
                if msg.tool_calls:
                    tc_json = json.dumps(
                        {"tool_calls": [{"name": tc["name"], "args": tc["args"], "id": tc["id"]} for tc in msg.tool_calls]}
                    )
                    formatted.append({"role": "assistant", "content": tc_json})
                else:
                    formatted.append({"role": "assistant", "content": msg.content})
            elif isinstance(msg, ToolMessage):
                formatted.append(
                    {"role": "user", "content": f"Tool result for {msg.name} (call_id={msg.tool_call_id}):\n{msg.content}"}
                )
        return formatted

    def _try_parse_tool_calls(self, content: str):
        if not content or not isinstance(content, str):
            return None
        text = content.strip()
        code_fence = re.search(r'```(?:json)?\s*\n?(.*?)```', text, re.DOTALL)
        if code_fence:
            text = code_fence.group(1).strip()
        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict) and "tool_calls" in parsed:
                return parsed["tool_calls"]
        except (json.JSONDecodeError, KeyError, TypeError):
            pass
        match = re.search(r'\{\s*"tool_calls"\s*:\s*\[', content)
        if match:
            start = match.start()
            depth = 0
            for i in range(start, len(content)):
                if content[i] == '{':
                    depth += 1
                elif content[i] == '}':
                    depth -= 1
                    if depth == 0:
                        try:
                            parsed = json.loads(content[start:i + 1])
                            if "tool_calls" in parsed:
                                return parsed["tool_calls"]
                        except (json.JSONDecodeError, KeyError, TypeError):
                            pass
                        break
        name_pattern = re.finditer(
            r'"name"\s*:\s*"([^"]+)"\s*,\s*"args"\s*:\s*(\{[^}]*\})',
            content
        )
        loose_calls = []
        for i, m in enumerate(name_pattern):
            try:
                args = json.loads(m.group(2))
                loose_calls.append({"name": m.group(1), "args": args, "id": f"call_{i+1}"})
            except json.JSONDecodeError:
                pass
        if loose_calls:
            return loose_calls
        return None

    def _generate(self, messages: list[BaseMessage], stop=None, run_manager=None, _retry_count=0, **kwargs) -> ChatResult:
        from snowflake.cortex import complete, CompleteOptions

        formatted = self._format_messages(messages)

        if self._tools:
            tool_schemas = self._build_tool_schema()
            tool_prompt = (
                "You have access to the following tools. When you want to call one or more tools, "
                "you MUST respond with ONLY a single JSON object and NO other text, in this exact format:\n"
                '{"tool_calls": [{"name": "<tool_name>", "args": {"query": "<search terms>"}, "id": "call_1"}]}\n\n'
                "Rules:\n"
                "- Put ALL parameters inside the \"args\" object.\n"
                "- You may call multiple tools at once by adding more entries to the tool_calls array.\n"
                "- If you do NOT need to use a tool, respond normally with text (no JSON).\n\n"
                f"Available tools:\n{json.dumps(tool_schemas, indent=2)}"
            )
            if formatted and formatted[0]["role"] == "system":
                formatted[0]["content"] += "\n\n" + tool_prompt
            else:
                formatted.insert(0, {"role": "system", "content": tool_prompt})

        options = CompleteOptions(temperature=self.temperature, max_tokens=self.max_tokens)
        content = complete(
            model=self.model_name,
            prompt=formatted,
            options=options,
            session=self.session,
        )

        usage_info = {}
        if hasattr(complete, 'get_last_usage'):
            usage_info = complete.get_last_usage()

        tool_calls = []
        parsed = self._try_parse_tool_calls(content)
        if parsed:
            for tc in parsed:
                tool_calls.append(ToolCall(
                    name=tc["name"],
                    args=tc["args"],
                    id=tc.get("id", f"call_{tc['name']}"),
                ))
            content = ""
        elif content and self._tools and not any(kw in content.lower() for kw in ["based on", "in summary", "in conclusion", "the answer"]):
            has_tool_hint = any(t.name in content for t in self._tools)
            if has_tool_hint:
                if _retry_count < 1:
                    logger.warning("LLM mentioned tool names but no parseable tool call found — requesting structured retry")
                    messages.append(AIMessage(content=content))
                    messages.append(HumanMessage(content=(
                        "You mentioned using a tool but did not provide the required JSON format. "
                        "Please respond with ONLY the JSON object, no other text:\n"
                        '{"tool_calls": [{"name": "<tool_name>", "args": {"query": "<search terms>"}, "id": "call_1"}]}'
                    )))
                    return self._generate(messages, stop=stop, run_manager=run_manager, _retry_count=_retry_count + 1, **kwargs)

        usage_meta = None
        if usage_info:
            usage_meta = UsageMetadata(
                input_tokens=usage_info.get("prompt_tokens", 0),
                output_tokens=usage_info.get("completion_tokens", 0),
                total_tokens=usage_info.get("total_tokens", 0),
            )

        ai_msg = AIMessage(content=content, tool_calls=tool_calls, usage_metadata=usage_meta)
        llm_output = {}
        if usage_info:
            llm_output = {
                "token_usage": usage_info,
                "model_name": usage_info.get("model", self.model_name),
            }
        return ChatResult(
            generations=[ChatGeneration(message=ai_msg)],
            llm_output=llm_output,
        )


def instrument_for_trulens():
    from trulens.core.otel.instrument import instrument_method
    from trulens.otel.semconv.trace import SpanAttributes

    _CORTEX_COSTS_PER_1M = {
        "claude-3-5-sonnet":   {"input": 1.50, "output": 7.50},
        "claude-3-7-sonnet":   {"input": 1.50, "output": 7.50},
        "claude-4-sonnet":     {"input": 1.50, "output": 7.50},
        "claude-4-5-sonnet":   {"input": 1.65, "output": 8.25},
        "claude-haiku-4-5":    {"input": 0.55, "output": 2.75},
        "claude-opus-4-5":     {"input": 2.75, "output": 13.75},
        "deepseek-r1":         {"input": 0.68, "output": 2.70},
        "llama3.1-405b":       {"input": 1.20, "output": 1.20},
        "llama3.1-70b":        {"input": 0.36, "output": 0.36},
        "llama3.1-8b":         {"input": 0.11, "output": 0.11},
        "llama3.3-70b":        {"input": 0.36, "output": 0.36},
        "llama4-maverick":     {"input": 0.12, "output": 0.49},
        "llama4-scout":        {"input": 0.09, "output": 0.33},
        "mistral-large2":      {"input": 1.00, "output": 3.00},
        "openai-gpt-4.1":      {"input": 1.00, "output": 4.00},
        "snowflake-llama-3.3-70b": {"input": 0.29, "output": 0.29},
    }

    _MODEL_NAME_MAP = {
        "claude-sonnet-4-5": "claude-4-5-sonnet",
        "claude-sonnet-4": "claude-4-sonnet",
        "claude-opus-4-6": "claude-opus-4-5",
        "claude-opus-4": "claude-opus-4-5",
    }

    def _compute_credits(model, prompt_tokens, completion_tokens):
        canonical = _MODEL_NAME_MAP.get(model, model)
        rates = _CORTEX_COSTS_PER_1M.get(canonical)
        if not rates:
            return 0.0
        return (prompt_tokens / 1_000_000 * rates["input"]) + (completion_tokens / 1_000_000 * rates["output"])

    def _extract_cost_attributes(ret, exception, *args, **kwargs):
        attrs = {}
        if ret and hasattr(ret, 'llm_output') and ret.llm_output:
            usage = ret.llm_output.get("token_usage", {})
            model = ret.llm_output.get("model_name", "")
            prompt_tokens = usage.get("prompt_tokens", 0)
            completion_tokens = usage.get("completion_tokens", 0)
            total_tokens = usage.get("total_tokens", 0)
            credits = _compute_credits(model, prompt_tokens, completion_tokens)
            attrs[SpanAttributes.COST.MODEL] = model
            attrs[SpanAttributes.COST.CURRENCY] = "Snowflake credits"
            attrs[SpanAttributes.COST.COST] = credits
            attrs[SpanAttributes.COST.NUM_TOKENS] = total_tokens
            attrs[SpanAttributes.COST.NUM_PROMPT_TOKENS] = prompt_tokens
            attrs[SpanAttributes.COST.NUM_COMPLETION_TOKENS] = completion_tokens
        return attrs

    instrument_method(
        cls=ChatCortexSQL,
        method_name="_generate",
        span_type=SpanAttributes.SpanType.GENERATION,
        attributes=_extract_cost_attributes,
    )


instrument_for_trulens()
