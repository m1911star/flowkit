"""Flowkit DSL v1 — Schema Models.

Pydantic v2 models for workflow definitions, nodes, edges, and per-node configs.
"""

from __future__ import annotations

import re
from enum import StrEnum
from typing import Any, cast

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

NODE_ID_PATTERN = re.compile(r"^[a-z0-9_]+$")
WORKFLOW_NAME_PATTERN = re.compile(r"^[a-z0-9-]+$")


class DataType(StrEnum):
    """Supported variable types in DSL v1."""

    string = "string"
    number = "number"
    boolean = "boolean"
    object = "object"
    array = "array"
    any = "any"


class NodeType(StrEnum):
    """Supported node types in DSL v1 MVP."""

    start = "start"
    end = "end"
    http = "http"
    code = "code"
    if_else = "if_else"
    loop = "loop"
    human_input = "human_input"


class HttpMethod(StrEnum):
    """HTTP methods supported by the http node."""

    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    PATCH = "PATCH"
    DELETE = "DELETE"


class BackoffStrategy(StrEnum):
    """Retry backoff strategies."""

    fixed = "fixed"
    exponential = "exponential"


# ---------------------------------------------------------------------------
# Input / Output Definitions
# ---------------------------------------------------------------------------


class InputDef(BaseModel):
    """Workflow-level input parameter definition."""

    model_config = ConfigDict(extra="forbid")

    type: DataType
    required: bool = False
    default: Any = None
    enum: list[Any] | None = None
    description: str | None = None


class OutputDef(BaseModel):
    """Workflow-level output declaration."""

    model_config = ConfigDict(extra="forbid")

    type: DataType
    value: str | None = None
    description: str | None = None


# ---------------------------------------------------------------------------
# Node Config Models
# ---------------------------------------------------------------------------


class RetryConfig(BaseModel):
    """Retry policy for HTTP requests."""

    model_config = ConfigDict(extra="forbid")

    max_attempts: int = Field(default=1, ge=1)
    backoff: BackoffStrategy = BackoffStrategy.fixed


class HttpNodeConfig(BaseModel):
    """Config for 'http' node type."""

    model_config = ConfigDict(extra="forbid")

    method: HttpMethod
    url: str
    headers: dict[str, str] = Field(default_factory=dict)
    body: str | dict[str, Any] | None = None
    timeout: int = Field(default=30, gt=0)
    retry: RetryConfig | None = None


class CodeNodeConfig(BaseModel):
    """Config for 'code' node type."""

    model_config = ConfigDict(extra="forbid")

    language: str
    source: str
    inputs: dict[str, str] = Field(default_factory=dict)


class Condition(BaseModel):
    """A single condition in an if_else node."""

    model_config = ConfigDict(extra="forbid")

    id: str
    expression: str


class IfElseConfig(BaseModel):
    """Config for 'if_else' node type."""

    model_config = ConfigDict(extra="forbid")

    conditions: list[Condition]


class LoopConfig(BaseModel):
    """Config for 'loop' node type."""

    model_config = ConfigDict(extra="forbid")

    items: str
    item_variable: str = "item"
    index_variable: str = "index"
    max_iterations: int = Field(default=100, ge=1)


class HumanInputConfig(BaseModel):
    """Config for 'human_input' node type."""

    model_config = ConfigDict(extra="forbid")

    prompt: str
    input_schema: dict[str, Any] = Field(default_factory=dict)
    timeout: int = Field(default=86400, gt=0)


class EndNodeConfig(BaseModel):
    """Config for 'end' node type."""

    model_config = ConfigDict(extra="forbid")

    output_mapping: dict[str, str] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Position
# ---------------------------------------------------------------------------


class Position(BaseModel):
    """UI position hint. Ignored by engine."""

    model_config = ConfigDict(extra="forbid")

    x: float
    y: float


# ---------------------------------------------------------------------------
# Node Definition
# ---------------------------------------------------------------------------


class NodeDef(BaseModel):
    """A single node in the workflow graph."""

    model_config = ConfigDict(extra="forbid")

    id: str
    type: NodeType
    label: str | None = None
    config: dict[str, Any] | None = None
    position: Position | None = None

    @field_validator("id")
    @classmethod
    def validate_id_format(cls, v: str) -> str:
        if not NODE_ID_PATTERN.match(v):
            msg = f"Node id must match [a-z0-9_]+, got '{v}'"
            raise ValueError(msg)
        return v

    def parsed_config(
        self,
    ) -> (
        HttpNodeConfig
        | CodeNodeConfig
        | IfElseConfig
        | LoopConfig
        | HumanInputConfig
        | EndNodeConfig
        | None
    ):
        """Parse the raw config dict into the typed config model for this node type."""
        if self.config is None:
            return None

        config_map: dict[NodeType, type[BaseModel]] = {
            NodeType.http: HttpNodeConfig,
            NodeType.code: CodeNodeConfig,
            NodeType.if_else: IfElseConfig,
            NodeType.loop: LoopConfig,
            NodeType.human_input: HumanInputConfig,
            NodeType.end: EndNodeConfig,
        }
        model_cls = config_map.get(self.type)
        if model_cls is None:
            return None
        result = model_cls.model_validate(self.config)
        return cast(
            "HttpNodeConfig | CodeNodeConfig | IfElseConfig | LoopConfig | "
            "HumanInputConfig | EndNodeConfig",
            result,
        )


# ---------------------------------------------------------------------------
# Edge Definition
# ---------------------------------------------------------------------------


class EdgeDef(BaseModel):
    """A directed edge connecting two nodes."""

    model_config = ConfigDict(extra="forbid")

    id: str
    source: str
    target: str
    source_handle: str = "default"
    target_handle: str = "default"


# ---------------------------------------------------------------------------
# Workflow Metadata
# ---------------------------------------------------------------------------


class WorkflowMetadata(BaseModel):
    """Human-readable workflow metadata."""

    model_config = ConfigDict(extra="forbid")

    name: str
    description: str | None = None

    @field_validator("name")
    @classmethod
    def validate_name_format(cls, v: str) -> str:
        if not WORKFLOW_NAME_PATTERN.match(v):
            msg = f"Workflow name must match [a-z0-9-]+, got '{v}'"
            raise ValueError(msg)
        return v


# ---------------------------------------------------------------------------
# Top-Level Workflow Definition
# ---------------------------------------------------------------------------


class WorkflowDefinition(BaseModel):
    """Complete workflow definition — the top-level DSL v1 document."""

    model_config = ConfigDict(extra="forbid")

    version: str
    metadata: WorkflowMetadata
    inputs: dict[str, InputDef] = Field(default_factory=dict)
    outputs: dict[str, OutputDef] = Field(default_factory=dict)
    nodes: list[NodeDef]
    edges: list[EdgeDef]

    @model_validator(mode="after")
    def validate_version(self) -> WorkflowDefinition:
        if self.version != "1.0":
            msg = f"Unsupported DSL version '{self.version}', expected '1.0'"
            raise ValueError(msg)
        return self
