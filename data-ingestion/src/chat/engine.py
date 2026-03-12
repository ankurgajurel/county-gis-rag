"""Chat engine: manages the conversation loop with OpenAI Responses API."""

import json
import logging
from collections.abc import AsyncGenerator

from openai import AsyncOpenAI

from src.chat.reasoning_parser import parse_reasoning
from src.chat.system_prompt import build_system_prompt
from src.chat.tool_schemas import TOOL_SCHEMAS
from src.chat.tools import TOOL_REGISTRY
from src.config import settings

logger = logging.getLogger(__name__)

MAX_TOOL_ROUNDS = 10


class ChatEngine:
    def __init__(self):
        self.client = AsyncOpenAI(api_key=settings.openai_api_key)
        self.model = settings.openai_model
        self.conversation_input: list[dict] = []
        self.system_prompt: str | None = None
        self.last_response_id: str | None = None

    async def initialize(self):
        self.system_prompt = await build_system_prompt()
        self.conversation_input = []
        self.last_response_id = None

    def _build_input(self, user_message: str) -> list[dict]:
        return [
            {"role": "developer", "content": self.system_prompt},
            *self.conversation_input,
            {"role": "user", "content": user_message},
        ]

    async def chat_stream(self, user_message: str) -> AsyncGenerator[dict, None]:
        if not self.system_prompt:
            await self.initialize()

        self.conversation_input.append({"role": "user", "content": user_message})
        input_items = self._build_input(user_message)

        for _ in range(MAX_TOOL_ROUNDS):
            kwargs = {
                "model": self.model,
                "input": input_items,
                "tools": TOOL_SCHEMAS,
                "reasoning": {"effort": settings.reasoning_effort, "summary": "auto"},
                "stream": True,
            }
            if self.last_response_id:
                kwargs["previous_response_id"] = self.last_response_id

            stream = await self.client.responses.create(**kwargs)

            reasoning_buffer = ""
            function_calls: dict[str, dict] = {}
            has_function_calls = False
            response_id = None
            full_text = ""

            async for event in stream:
                if event.type == "response.created":
                    response_id = event.response.id

                elif event.type == "response.reasoning_summary_text.delta":
                    reasoning_buffer += event.delta
                    yield {"type": "reasoning_delta", "content": event.delta}

                elif event.type == "response.reasoning_summary_text.done":
                    if reasoning_buffer:
                        blocks = parse_reasoning(reasoning_buffer)
                        yield {"type": "reasoning_done", "blocks": blocks}
                        reasoning_buffer = ""

                elif event.type == "response.function_call_arguments.done":
                    has_function_calls = True
                    function_calls[event.item_id] = {
                        "name": event.name,
                        "arguments": event.arguments,
                    }

                elif event.type == "response.output_text.delta":
                    full_text += event.delta
                    yield {"type": "token", "content": event.delta}

                elif event.type == "response.completed":
                    self.last_response_id = response_id

            if has_function_calls:
                tool_names = [fc["name"] for fc in function_calls.values()]
                yield {"type": "tool_status", "tools": tool_names}

                tool_outputs = []
                for call_id, fc in function_calls.items():
                    result = await self._execute_tool_by_name(fc["name"], fc["arguments"])
                    tool_outputs.append({
                        "type": "function_call_output",
                        "call_id": call_id,
                        "output": json.dumps(result, default=str),
                    })

                yield {"type": "tool_status_end"}

                # Chain: next iteration uses previous_response_id + tool outputs
                input_items = tool_outputs
                continue

            # No function calls — response complete
            self.conversation_input.append({"role": "assistant", "content": full_text})
            return

        yield {"type": "token", "content": "I've made too many tool calls trying to answer this. Could you rephrase or simplify your question?"}

    async def chat(self, user_message: str) -> str:
        """Non-streaming chat (collects all tokens)."""
        if not self.system_prompt:
            await self.initialize()

        full_text = ""
        async for event in self.chat_stream(user_message):
            if event["type"] == "token":
                full_text += event["content"]
        return full_text

    async def _execute_tool_by_name(self, name: str, arguments_json: str) -> dict:
        try:
            args = json.loads(arguments_json)
        except json.JSONDecodeError:
            return {"error": f"Invalid arguments for {name}"}

        fn = TOOL_REGISTRY.get(name)
        if not fn:
            return {"error": f"Unknown tool: {name}"}

        logger.info("Calling tool %s(%s)", name, args)

        try:
            return await fn(**args)
        except Exception as e:
            logger.error("Tool %s failed: %s", name, e)
            return {"error": f"Tool {name} failed: {str(e)}"}
