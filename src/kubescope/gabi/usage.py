"""What an answer cost in tokens, as the program says it.

Claude Code and Codex report the tokens of each answer; the session adds
them up for the conversation. No Qt.
"""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Usage:
    input_tokens: int = 0  # what was read fresh, not from the cache
    output_tokens: int = 0
    cache_read: int = 0  # read from the cache of the prompt
    cache_write: int = 0  # written to the cache of the prompt
    cost: float | None = None  # in dollars, when the program tells
    cache_ttl: int = 0  # seconds the cache it wrote is kept; 0 when not told

    def __add__(self, other: Usage) -> Usage:
        cost = None if self.cost is None and other.cost is None else 0.0
        if cost is not None:
            cost = (self.cost or 0.0) + (other.cost or 0.0)
        return Usage(
            self.input_tokens + other.input_tokens,
            self.output_tokens + other.output_tokens,
            self.cache_read + other.cache_read,
            self.cache_write + other.cache_write,
            cost,
            max(self.cache_ttl, other.cache_ttl),
        )

    @property
    def context(self) -> int:
        """Everything the program was given: fresh, cached and just cached."""
        return self.input_tokens + self.cache_read + self.cache_write

    @property
    def cache_hit(self) -> float:
        """The share of what it was given that came from the cache, 0 to 1."""
        return self.cache_read / self.context if self.context else 0.0

    def __bool__(self) -> bool:
        return bool(self.context or self.output_tokens)


def compact(number: int) -> str:
    """12345 as 12.3k, so it fits a line of the header."""
    if number < 1000:
        return str(number)
    if number < 1_000_000:
        return f"{number / 1000:.1f}k"
    return f"{number / 1_000_000:.1f}M"


def count(value: object) -> int:
    """A token count from a document of the program; anything else is 0."""
    return value if type(value) is int and value >= 0 else 0
