"""Preference cards: what a surgeon wants for a procedure.

The card is where the department finds out what a case needs, and it is
almost always slightly wrong, because surgeons change their minds faster than
anybody updates the card. So it is versioned the same way a count sheet is, and
the card that matters is the one in force on the day of the case rather than
the one somebody edited last week.

Essential lines are the ones that stop the case. Everything else is a
preference in the ordinary sense, and a missing preference is an annoyance
rather than a delay.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date

from sterilot.errors import NotFoundError, ValidationError
from sterilot.ids import normalise_code, tray_code
from sterilot.interval import DateRange


@dataclass(frozen=True)
class CardLine:
    """One set the card calls for."""

    code: str
    quantity: int = 1
    essential: bool = True
    note: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "code", tray_code(self.code))
        if self.quantity < 1:
            raise ValidationError("a card line asks for at least one", code=self.code)

    def describe(self) -> str:
        weight = "essential" if self.essential else "preferred"
        because = f", {self.note}" if self.note else ""
        return f"{self.quantity} x {self.code} ({weight}){because}"


@dataclass(frozen=True)
class PreferenceCard:
    """One surgeon, one procedure, one version."""

    reference: str
    surgeon: str
    procedure: str
    lines: tuple[CardLine, ...]
    effective: DateRange
    revision: int = 1
    loaner_sets: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "reference", normalise_code(self.reference, field="card reference")
        )
        if not self.surgeon.strip():
            raise ValidationError("a card names a surgeon", reference=self.reference)
        if not self.procedure.strip():
            raise ValidationError("a card names a procedure", reference=self.reference)
        if not self.lines:
            raise ValidationError("a card asks for something", reference=self.reference)
        if self.revision < 1:
            raise ValidationError("revisions are numbered from one", reference=self.reference)
        codes = [line.code for line in self.lines]
        if len(set(codes)) != len(codes):
            raise ValidationError("the same set is on two lines", reference=self.reference)

    @classmethod
    def of(
        cls,
        reference: str,
        surgeon: str,
        procedure: str,
        lines: Iterable[CardLine],
        effective: DateRange,
        **values: object,
    ) -> PreferenceCard:
        return cls(reference, surgeon, procedure, tuple(lines), effective, **values)  # type: ignore[arg-type]

    def in_force_on(self, day: date) -> bool:
        return self.effective.contains(day)

    def line_for(self, code: str) -> CardLine:
        wanted = tray_code(code)
        for line in self.lines:
            if line.code == wanted:
                return line
        raise NotFoundError("that set is not on this card", reference=self.reference, code=wanted)

    def calls_for(self, code: str) -> bool:
        try:
            self.line_for(code)
        except NotFoundError:
            return False
        return True

    def essential_lines(self) -> tuple[CardLine, ...]:
        return tuple(line for line in self.lines if line.essential)

    def wanted(self, essential_only: bool = False) -> dict[str, int]:
        lines = self.essential_lines() if essential_only else self.lines
        return {line.code: line.quantity for line in lines}

    @property
    def total_sets(self) -> int:
        return sum(line.quantity for line in self.lines)

    @property
    def needs_loaner(self) -> bool:
        return bool(self.loaner_sets)

    def revised(
        self, lines: Iterable[CardLine], effective_from: date, **values: object
    ) -> PreferenceCard:
        """Close this card and open the next revision."""
        if effective_from <= self.effective.start:
            raise ValidationError(
                "a revision cannot start before the card it replaces", reference=self.reference
            )
        return PreferenceCard.of(
            self.reference,
            self.surgeon,
            self.procedure,
            lines,
            DateRange.starting(effective_from),
            revision=self.revision + 1,
            **values,
        )

    def label(self) -> str:
        return f"{self.reference} {self.surgeon} {self.procedure} rev {self.revision}"

    def __str__(self) -> str:
        return self.label()


@dataclass(frozen=True)
class CardFile:
    """Every card the department holds."""

    cards: tuple[PreferenceCard, ...] = ()

    def with_card(self, card: PreferenceCard) -> CardFile:
        return CardFile((*self.cards, card))

    def for_reference(self, reference: str, day: date) -> PreferenceCard:
        wanted = normalise_code(reference, field="card reference")
        for card in self.cards:
            if card.reference == wanted and card.in_force_on(day):
                return card
        raise NotFoundError(
            "no card in force with that reference", reference=wanted, day=day.isoformat()
        )

    def for_surgeon(self, surgeon: str, day: date) -> tuple[PreferenceCard, ...]:
        wanted = surgeon.strip().casefold()
        return tuple(
            card
            for card in self.cards
            if card.surgeon.casefold() == wanted and card.in_force_on(day)
        )

    def sets_used_by(self, code: str, day: date) -> tuple[str, ...]:
        """Which cards call for a set, which is what a par level is built from."""
        return tuple(
            sorted(
                card.reference
                for card in self.cards
                if card.in_force_on(day) and card.calls_for(code)
            )
        )
