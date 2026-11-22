import json

from kubescope.gabi import claude, codex
from kubescope.gabi.usage import Usage, compact, count


def test_usages_add_up_and_tell_the_share_that_came_from_the_cache() -> None:
    total = Usage(10, 5, 80, 10, None) + Usage(0, 1, 0, 0, 0.25)

    assert total == Usage(10, 6, 80, 10, 0.25)
    assert total.context == 100 and total.cache_hit == 0.8
    assert Usage(1, 0, 0, 0, 0.5) + Usage(1, 0, 0, 0, 0.5) == Usage(2, 0, 0, 0, 1.0)
    assert not Usage() and Usage(output_tokens=1) and Usage().cache_hit == 0.0


def test_numbers_are_shortened_and_bad_counts_are_zero() -> None:
    assert [compact(n) for n in (7, 12_345, 2_500_000)] == ["7", "12.3k", "2.5M"]
    assert [count(v) for v in (5, -1, "5", True, None)] == [5, 0, 0, 0, 0]


def test_claude_reports_the_tokens_on_its_result_line() -> None:
    line = json.dumps(
        {
            "type": "result",
            "total_cost_usd": 0.02,
            "usage": {
                "input_tokens": 3,
                "output_tokens": 7,
                "cache_read_input_tokens": 100,
                "cache_creation_input_tokens": 9,
            },
        }
    )

    assert claude.parse_usage(line) == Usage(3, 7, 100, 9, 0.02)
    assert claude.parse_usage(json.dumps({"type": "result"})) == Usage()
    assert claude.parse_usage(json.dumps({"type": "assistant"})) is None
    assert claude.parse_usage("a notice") is None


def test_codex_reports_the_tokens_of_a_turn_with_the_cache_taken_out() -> None:
    line = json.dumps(
        {
            "type": "turn.completed",
            "usage": {
                "input_tokens": 120,
                "cached_input_tokens": 100,
                "output_tokens": 4,
            },
        }
    )

    assert codex.parse_usage(line) == Usage(20, 4, 100)
    assert codex.parse_usage(json.dumps({"type": "turn.started"})) is None
    assert codex.parse_usage("a notice") is None
