"""Abstract base class for all Nova modules (tools)."""

from abc import ABC, abstractmethod


class NovaModule(ABC):
    """
    Base class every Nova module must inherit from.

    Subclasses define name, description, and parameters as class-level
    attributes, and implement the async run() method.
    """

    name: str = ""
    description: str = ""
    parameters: dict = {}

    @abstractmethod
    async def run(self, **kwargs) -> str:
        """
        Execute the tool with the provided keyword arguments.

        Must catch all exceptions internally and return a human-readable
        error string rather than propagating exceptions.

        Returns:
            str: The result of the tool execution, or an error message.
        """

    def to_tool_definition(self) -> dict:
        """
        Return the tool definition dict in the format expected by Ollama's
        tool-calling API.
        """
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }
