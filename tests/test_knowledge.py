from kubescope.gabi.knowledge import language_rule, system_prompt


def test_the_assistant_is_told_the_language_of_the_client_and_the_ones_it_has() -> None:
    rule = language_rule("Portuguese", ("English", "German", "Portuguese"))

    assert "Answer in Portuguese, the language of the client" in rule
    assert "language of the client: English, German, Portuguese." in rule


def test_without_a_list_only_english_is_said() -> None:
    assert "language of the client: English." in language_rule("English")


def test_the_prompt_carries_the_language_rule_and_follows_the_write_mode() -> None:
    on = system_prompt("German", True, ("English", "German"))
    off = system_prompt("German", False, ("English", "German"))

    assert "Answer in German" in on and "English, German" in on
    assert (
        on != off
    )  # with the write mode off nothing that changes a cluster is offered
