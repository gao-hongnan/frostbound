import subprocess
from enum import Enum
from pathlib import Path
from typing import Any, Callable

from pydantic import BaseModel, ConfigDict, Field, field_validator


class GitField(str, Enum):
    COMMIT = "commit"
    SHORT_COMMIT = "short_commit"
    BRANCH = "branch"
    IS_DIRTY = "is_dirty"


class GitFieldSpec(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    field: GitField
    command: list[str]
    processor: Callable[[str], Any] = Field(default=lambda x: x)

    @field_validator("command")
    @classmethod
    def validate_command(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("Command cannot be empty")
        return v


class GitInfo(BaseModel):
    commit: str | None = None
    short_commit: str | None = None
    branch: str | None = None
    is_dirty: bool | None = None


class GitInfoConfig(BaseModel):
    fields: list[GitFieldSpec] = Field(
        default_factory=lambda: [
            GitFieldSpec(field=GitField.COMMIT, command=["rev-parse", "HEAD"]),
            GitFieldSpec(field=GitField.SHORT_COMMIT, command=["rev-parse", "--short=7", "HEAD"]),
            GitFieldSpec(field=GitField.BRANCH, command=["rev-parse", "--abbrev-ref", "HEAD"]),
            GitFieldSpec(field=GitField.IS_DIRTY, command=["status", "--porcelain"], processor=lambda x: bool(x)),
        ]
    )


def get_git_info(repo_path: Path | None = None, config: GitInfoConfig | None = None) -> GitInfo:
    if config is None:
        config = GitInfoConfig()

    def execute_git_command(cmd: list[str]) -> str | None:
        try:
            result = subprocess.run(["git"] + cmd, capture_output=True, text=True, cwd=repo_path, check=True)
            return result.stdout.strip()
        except (subprocess.CalledProcessError, FileNotFoundError):
            return None

    git_data = {}
    for spec in config.fields:
        output = execute_git_command(spec.command)
        if output is not None:
            git_data[spec.field.value] = spec.processor(output)
        else:
            git_data[spec.field.value] = None

    return GitInfo(**git_data)
