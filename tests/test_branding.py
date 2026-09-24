from chalk.branding import PROJECT_NAME


def test_project_name_is_chalk():
    """Working name locked in during the pre-build interview (DECISIONS.md)."""
    assert PROJECT_NAME == "Chalk"
