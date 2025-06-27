"""Define the configurable parameters for the agent."""

from pathlib import Path
from typing import Any, Literal

import yaml
from langchain_core.runnables import ensure_config
from langgraph.config import get_config
from pydantic import BaseModel, Field

from hi.graph import prompts

DEFAULT_CONFIG_PATH = Path("~/.config/hi/config.yaml").expanduser().resolve()
DEFAULT_ENV_PATH = Path("~/.config/hi/env").expanduser().resolve()


class ModelConfig(BaseModel):
    """Configuration for a language model used by the agent."""

    fully_specified_name: str = Field(
        default="openai/qwen-turbo",
        description="The fully specified name of the model to use, in the format 'provider/model'. "
        "For example, 'openai/qwen-turbo' or 'anthropic/claude-3.5'.",
    )
    api_key: str | None = None
    base_url: str | None = None
    kwargs: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional keyword arguments for the model, such as temperature, max_tokens, etc.",
    )


class Configuration(BaseModel):
    """The configuration for the agent."""

    smart_model: ModelConfig = Field(default_factory=ModelConfig)
    fast_model: ModelConfig | None = Field(
        default=None,
        description="Configuration for a fast model, if available. "
        "This can be used for quick responses or fallback options.",
    )
    default_model: Literal["smart", "fast"] = Field(
        default="smart",
        description="The default model to use for the agent. "
        "This can be set to 'smart' or 'fast' depending on the available models.",
    )

    system_prompt: str = Field(
        default=prompts.SYSTEM_PROMPT,
        description="The system prompt to use for the agent's interactions. "
        "This prompt sets the context and behavior for the agent.",
    )

    command_timeout: float = Field(
        default=30,
        description="The timeout in seconds for executing commands. "
        "This is used to limit how long the agent waits for command execution.",
    )

    @classmethod
    def from_context(cls) -> "Configuration":
        """Create a Configuration instance from a RunnableConfig object."""
        try:
            config = get_config()
        except RuntimeError:
            config = None
        config = ensure_config(config)
        configurable = config.get("configurable") or {}

        return cls.model_validate(configurable)


def setup_config():
    """Set up the configuration file and return whether it was created."""
    default_path = DEFAULT_CONFIG_PATH
    default_path.parent.mkdir(parents=True, exist_ok=True)

    if not default_path.exists():
        default_config = Configuration().model_dump()
        del default_config["system_prompt"]
        with open(default_path, "w") as f:
            yaml.safe_dump(default_config, f)

        return True

    return False


def load_config(path: str) -> Configuration:
    with open(path) as f:
        config_dict = yaml.load(f, Loader=yaml.FullLoader) or {}

    config_obj = Configuration.model_validate(config_dict)

    return config_obj
