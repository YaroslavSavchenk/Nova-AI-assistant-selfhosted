"""
Tool router — module registry and dispatcher for Nova.

Modules register themselves here. The router converts them to Ollama tool
definitions and dispatches tool calls from the LLM to the right module.
"""

import logging
from modules.base import NovaModule

logger = logging.getLogger(__name__)


class ToolRouter:
    """Registry and dispatcher for Nova tool modules."""

    def __init__(self) -> None:
        self._modules: dict[str, NovaModule] = {}

    def register(self, module: NovaModule) -> None:
        """
        Register a module with the router.

        Args:
            module: An instance of a NovaModule subclass.
        """
        if not module.name:
            raise ValueError("Module must have a non-empty name")
        self._modules[module.name] = module
        logger.debug("Registered module: %s", module.name)

    def get_tool_definitions(self) -> list[dict]:
        """
        Return Ollama-compatible tool definitions for all registered modules.
        """
        return [module.to_tool_definition() for module in self._modules.values()]

    async def dispatch(self, tool_name: str, tool_args: dict) -> str:
        """
        Dispatch a tool call to the matching module.

        Args:
            tool_name: The name of the tool to call.
            tool_args: Keyword arguments to pass to the module's run().

        Returns:
            The string result from the module, or a human-readable error.
        """
        module = self._modules.get(tool_name)
        if module is None:
            logger.warning("Tool not found: %s", tool_name)
            return f"Tool not found: {tool_name}"

        logger.debug("Dispatching tool '%s' with args: %s", tool_name, tool_args)
        result = await module.run(**tool_args)
        return result
