"""Single source of truth for the product name.

Every user-facing surface — the Streamlit page title, the README heading,
the Canvas HTML export's header comment, the CLI banner — must import
PROJECT_NAME from here rather than hardcoding the name. That keeps a
future rename to a one-line change instead of a repo-wide find-and-replace.

Working name as of the pre-build interview (see DECISIONS.md): "Chalk".
"""

PROJECT_NAME = "Chalk"
