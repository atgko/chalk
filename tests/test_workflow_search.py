from chalk.generation.specs import SPECS
from ui.shell import TAB_NAMES
from ui.workflow_search import WORKFLOWS


def test_every_workflow_opens_a_real_tab():
    assert {workflow.tab for workflow in WORKFLOWS} <= set(TAB_NAMES)


def test_every_tab_has_a_workflow():
    assert {workflow.tab for workflow in WORKFLOWS} == set(TAB_NAMES)


def test_every_generation_type_is_a_real_content_type():
    types = [w.generation_type for w in WORKFLOWS if w.generation_type is not None]
    assert sorted(types) == sorted(SPECS)


def test_workflow_keys_are_unique():
    keys = [workflow.key for workflow in WORKFLOWS]
    assert len(keys) == len(set(keys))


def test_labels_carry_the_words_people_type():
    # The dropdown only filters on what it shows, so the words people use
    # for a tab they can't name have to be in the label.
    labels = " ".join(workflow.label for workflow in WORKFLOWS)
    for word in ("Canvas", "PowerPoint", "sessions", "drafts", "Grade"):
        assert word in labels
