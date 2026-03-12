"""Chat engine: manages the conversation loop with OpenAI tool calling."""

import json
import logging

from openai import AsyncOpenAI

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
        self.messages: list[dict] = []
        self.system_prompt: str | None = None

    async def initialize(self):
        self.system_prompt = await build_system_prompt()
        self.messages = []

    async def chat(self, user_message: str) -> str:
        if not self.system_prompt:
            await self.initialize()

        self.messages.append({"role": "user", "content": user_message})

        for _ in range(MAX_TOOL_ROUNDS):
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": self.system_prompt},
                    *self.messages,
                ],
                tools=TOOL_SCHEMAS,
            )

            choice = response.choices[0]

            if choice.finish_reason == "tool_calls":
                self.messages.append(choice.message.model_dump())

                for tool_call in choice.message.tool_calls:
                    result = await self._execute_tool(tool_call)
                    self.messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": json.dumps(result, default=str),
                    })

                continue

            assistant_text = choice.message.content or ""
            self.messages.append({"role": "assistant", "content": assistant_text})
            return assistant_text

        return "I've made too many tool calls trying to answer this. Could you rephrase or simplify your question?"

    async def _execute_tool(self, tool_call) -> dict:
        name = tool_call.function.name
        try:
            args = json.loads(tool_call.function.arguments)
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
