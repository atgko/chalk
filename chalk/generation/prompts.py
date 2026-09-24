"""Prompt templates: load from the project's prompts/ folder, validate,
and fill in.

Validation (DECISIONS.md): a template missing a required `{variable}`
raises PromptTemplateError naming the variable and the file — no
auto-repair. Filling replaces only known `{variable}` names, so any other
braces an instructor types (or Pandoc's `{.columns}` syntax in the slides
template) pass through untouched instead of crashing str.format().

If the project has no copy of a template at all (a project created
before that content type existed), the toolkit's bundled default is used.
A template the instructor *has* edited is never silently replaced.
"""

from __future__ import annotations

import re
from pathlib import Path

from chalk.errors import PromptTemplateError
from chalk.generation.specs import ContentSpec
from chalk.project import RESOURCES_DIR

_PLACEHOLDER_RE = re.compile(r"\{([a-z_]+)\}")


def template_path(prompts_dir: Path, spec: ContentSpec, *, resources_dir: Path = RESOURCES_DIR) -> Path:
    project_copy = prompts_dir / spec.template_name
    return project_copy if project_copy.exists() else resources_dir / "prompts" / spec.template_name


def load_template(prompts_dir: Path, spec: ContentSpec, *, resources_dir: Path = RESOURCES_DIR) -> str:
    path = template_path(prompts_dir, spec, resources_dir=resources_dir)
    try:
        template = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise PromptTemplateError(
            f"The prompt template {path} couldn't be read. Make sure it exists and is saved as UTF-8 text."
        ) from exc

    present = set(_PLACEHOLDER_RE.findall(template))
    missing = [name for name in spec.required_variables if name not in present]
    if missing:
        names = ", ".join(f"{{{name}}}" for name in missing)
        raise PromptTemplateError(
            f"The prompt template {path} is missing {names}. Add it back where that information "
            "should go, then try again."
        )
    return template


def fill_template(template: str, variables: dict[str, str]) -> str:
    return _PLACEHOLDER_RE.sub(lambda m: variables.get(m.group(1), m.group(0)), template)
