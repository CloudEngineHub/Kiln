from typing import TYPE_CHECKING, Dict, List, Union

from pydantic import BaseModel, Field, ValidationInfo, model_validator
from typing_extensions import Self

from kiln_ai.datamodel import Finetune
from kiln_ai.datamodel.basemodel import (
    ID_FIELD,
    ID_TYPE,
    FilenameString,
    FilenameStringShort,
    KilnParentedModel,
    KilnParentModel,
)
from kiln_ai.datamodel.datamodel_enums import (
    ModelProviderName,
    Priority,
    StructuredOutputMode,
    TaskOutputRatingType,
)
from kiln_ai.datamodel.dataset_split import DatasetSplit
from kiln_ai.datamodel.eval import Eval
from kiln_ai.datamodel.json_schema import JsonObjectSchema, schema_from_json_str
from kiln_ai.datamodel.prompt import BasePrompt, Prompt
from kiln_ai.datamodel.prompt_id import PromptId
from kiln_ai.datamodel.task_run import TaskRun

if TYPE_CHECKING:
    from kiln_ai.datamodel.project import Project


class TaskRequirement(BaseModel):
    """
    Defines a specific requirement that should be met by task outputs.

    Includes an identifier, name, description, instruction for meeting the requirement,
    priority level, and rating type (five_star, pass_fail, pass_fail_critical, custom).
    """

    id: ID_TYPE = ID_FIELD
    name: FilenameStringShort = Field(description="The name of the task requirement.")
    description: str | None = Field(default=None)
    instruction: str = Field(min_length=1)
    priority: Priority = Field(default=Priority.p2)
    type: TaskOutputRatingType = Field(default=TaskOutputRatingType.five_star)


class RunConfigProperties(BaseModel):
    """
    A configuration for running a task.

    This includes everything needed to run a task, except the input and task ID. Running the same RunConfig with the same input should make identical calls to the model (output may vary as models are non-deterministic).
    """

    model_name: str = Field(description="The model to use for this run config.")
    model_provider_name: ModelProviderName = Field(
        description="The provider to use for this run config."
    )
    prompt_id: PromptId = Field(
        description="The prompt to use for this run config. Defaults to building a simple prompt from the task if not provided.",
    )
    top_p: float = Field(
        default=1.0,
        description="The top-p value to use for this run config. Defaults to 1.0.",
    )
    temperature: float = Field(
        default=1.0,
        description="The temperature to use for this run config. Defaults to 1.0.",
    )
    structured_output_mode: StructuredOutputMode = Field(
        description="The structured output mode to use for this run config.",
    )

    @model_validator(mode="after")
    def validate_required_fields(self) -> Self:
        if not (0 <= self.top_p <= 1):
            raise ValueError("top_p must be between 0 and 1")

        elif self.temperature < 0 or self.temperature > 2:
            raise ValueError("temperature must be between 0 and 2")

        return self


class RunConfig(RunConfigProperties):
    """
    A configuration for running a task.

    This includes everything needed to run a task, except the input. Running the same RunConfig with the same input should make identical calls to the model (output may vary as models are non-deterministic).

    For example: task, model, provider, prompt, etc.
    """

    task: "Task" = Field(description="The task to run.")


class TaskRunConfig(KilnParentedModel):
    """
    A Kiln model for persisting a run config in a Kiln Project, nested under a task.

    Typically used to save a method of running a task for evaluation.

    A run config includes everything needed to run a task, except the input. Running the same RunConfig with the same input should make identical calls to the model (output may vary as models are non-deterministic).
    """

    name: FilenameString = Field(description="The name of the task run config.")
    description: str | None = Field(
        default=None, description="The description of the task run config."
    )
    run_config_properties: RunConfigProperties = Field(
        description="The run config properties to use for this task run."
    )
    # The prompt_id in the run_config_properties is the prompt ID to use for this task run.
    # However, we want the prompt to be perfectly consistent, and some prompt_ids are dynamic.
    # If we need to "freeze" a prompt, we can do so here (then point the prompt_id to this frozen prompt).
    prompt: BasePrompt | None = Field(
        default=None,
        description="A prompt to use for run config.",
    )

    # Workaround to return typed parent without importing Task
    def parent_task(self) -> Union["Task", None]:
        if self.parent is None or self.parent.__class__.__name__ != "Task":
            return None
        return self.parent  # type: ignore

    def run_config(self) -> RunConfig:
        parent_task = self.parent_task()
        if parent_task is None:
            raise ValueError("Run config must be parented to a task")
        return run_config_from_run_config_properties(
            task=parent_task,
            run_config_properties=self.run_config_properties,
        )

    # Previously we didn't store structured_output_mode in the run_config_properties. Updgrade old models when loading from file.
    @model_validator(mode="before")
    def upgrade_old_entries(cls, data: dict, info: ValidationInfo) -> dict:
        if not info.context or not info.context.get("loading_from_file", False):
            # Not loading from file, so no need to upgrade
            return data

        if not isinstance(data, dict):
            return data

        structured_output_mode = data.get("run_config_properties", {}).get(
            "structured_output_mode", None
        )
        if structured_output_mode is None and "run_config_properties" in data:
            # Default to unknown. Adapter will have to guess at runtime.
            data["run_config_properties"]["structured_output_mode"] = (
                StructuredOutputMode.unknown
            )

        return data


def run_config_from_run_config_properties(
    task: "Task",
    run_config_properties: RunConfigProperties,
) -> RunConfig:
    return RunConfig(
        task=task,
        model_name=run_config_properties.model_name,
        model_provider_name=run_config_properties.model_provider_name,
        prompt_id=run_config_properties.prompt_id,
        top_p=run_config_properties.top_p,
        temperature=run_config_properties.temperature,
        structured_output_mode=run_config_properties.structured_output_mode,
    )


class Task(
    KilnParentedModel,
    KilnParentModel,
    parent_of={
        "runs": TaskRun,
        "dataset_splits": DatasetSplit,
        "finetunes": Finetune,
        "prompts": Prompt,
        "evals": Eval,
        "run_configs": TaskRunConfig,
    },
):
    """
    Represents a specific task to be performed, with associated requirements and validation rules.

    Contains the task definition, requirements, input/output schemas, and maintains
    a collection of task runs.
    """

    name: FilenameString = Field(description="The name of the task.")
    description: str | None = Field(
        default=None,
        description="A description of the task for you and your team. Will not be used in prompts/training/validation.",
    )
    instruction: str = Field(
        min_length=1,
        description="The instructions for the task. Will be used in prompts/training/validation.",
    )
    requirements: List[TaskRequirement] = Field(default=[])
    output_json_schema: JsonObjectSchema | None = None
    input_json_schema: JsonObjectSchema | None = None
    thinking_instruction: str | None = Field(
        default=None,
        description="Instructions for the model 'thinking' about the requirement prior to answering. Used for chain of thought style prompting.",
    )

    def output_schema(self) -> Dict | None:
        if self.output_json_schema is None:
            return None
        return schema_from_json_str(self.output_json_schema)

    def input_schema(self) -> Dict | None:
        if self.input_json_schema is None:
            return None
        return schema_from_json_str(self.input_json_schema)

    # These wrappers help for typechecking. We should fix this in KilnParentModel
    def runs(self, readonly: bool = False) -> list[TaskRun]:
        return super().runs(readonly=readonly)  # type: ignore

    def dataset_splits(self, readonly: bool = False) -> list[DatasetSplit]:
        return super().dataset_splits(readonly=readonly)  # type: ignore

    def finetunes(self, readonly: bool = False) -> list[Finetune]:
        return super().finetunes(readonly=readonly)  # type: ignore

    def prompts(self, readonly: bool = False) -> list[Prompt]:
        return super().prompts(readonly=readonly)  # type: ignore

    def evals(self, readonly: bool = False) -> list[Eval]:
        return super().evals(readonly=readonly)  # type: ignore

    def run_configs(self, readonly: bool = False) -> list[TaskRunConfig]:
        return super().run_configs(readonly=readonly)  # type: ignore

    # Workaround to return typed parent without importing Task
    def parent_project(self) -> Union["Project", None]:
        if self.parent is None or self.parent.__class__.__name__ != "Project":
            return None
        return self.parent  # type: ignore
