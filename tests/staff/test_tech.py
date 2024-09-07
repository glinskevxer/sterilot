from __future__ import annotations

from datetime import date

import pytest

from sterilot.errors import ConflictError, NotFoundError, ValidationError
from sterilot.interval import DateRange
from sterilot.staff.tech import Certification, Role, Roster, Technician

DAY = date(2024, 9, 10)


def cert(start: date = date(2023, 1, 1), end: date | None = date(2026, 1, 1)) -> Certification:
    return Certification("hspa", "crcst 44821", DateRange(start, end))


def person(**changes: object) -> Technician:
    values: dict[str, object] = {
        "badge": "t 4471",
        "name": "R Ferreira",
        "role": Role.TECHNICIAN,
        "certifications": (cert(),),
    }
    values.update(changes)
    return Technician(**values)  # type: ignore[arg-type]


def test_roles_are_ranked_and_named() -> None:
    assert Role.named("supervisor") is Role.SUPERVISOR
    assert Role.TRAINEE.rank < Role.TECHNICIAN.rank < Role.LEAD.rank < Role.SUPERVISOR.rank
    with pytest.raises(ValidationError):
        Role.named("intern")


def test_who_may_do_what_by_role() -> None:
    assert not Role.TRAINEE.may_release
    assert Role.TECHNICIAN.may_release
    assert not Role.TECHNICIAN.may_authorise_early_release
    assert Role.LEAD.may_authorise_early_release
    assert Role.SUPERVISOR.may_close_a_recall
    assert not Role.LEAD.may_close_a_recall


def test_certifications_are_normalised_and_windowed() -> None:
    made = cert()
    assert made.body == "HSPA"
    assert made.number == "CRCST-44821"
    assert made.current_on(DAY)
    assert not cert(end=date(2024, 3, 1)).current_on(DAY)
    assert made.describe() == "HSPA CRCST-44821 2023-01-01 to 2025-12-31"


def test_a_technician_needs_a_name() -> None:
    with pytest.raises(ValidationError):
        person(name="  ")


def test_a_certified_technician_may_release() -> None:
    assert person().may_release(DAY)
    assert person().refusal_to_release(DAY) is None


def test_a_trainee_never_releases() -> None:
    assert person(role=Role.TRAINEE).refusal_to_release(DAY) == "a trainee does not sign a release"


def test_a_lapsed_certification_stops_a_release() -> None:
    lapsed = person(certifications=(cert(end=date(2024, 3, 1)),))
    assert lapsed.refusal_to_release(DAY) == "the certification is not current"
    assert lapsed.current_certifications(DAY) == ()


def test_no_certification_at_all_stops_a_release() -> None:
    assert not person(certifications=()).may_release(DAY)


def test_a_badge_that_has_left_stops_a_release_first() -> None:
    gone = person(
        employed=DateRange(date(2019, 1, 1), date(2024, 6, 1)),
        certifications=(),
        role=Role.TRAINEE,
    )
    assert gone.refusal_to_release(DAY) == "the badge is not employed on that day"


def test_a_technician_with_no_window_is_always_employed() -> None:
    assert person().employed_on(date(2030, 1, 1))


def test_only_a_lead_or_above_authorises_an_early_release() -> None:
    assert person().refusal_to_authorise(DAY) == (
        "a technician does not authorise an early release"
    )
    assert person(role=Role.LEAD).refusal_to_authorise(DAY) is None


def test_the_release_refusal_comes_before_the_authorisation_one() -> None:
    lapsed = person(role=Role.LEAD, certifications=(cert(end=date(2024, 3, 1)),))
    assert lapsed.refusal_to_authorise(DAY) == "the certification is not current"


def test_adding_a_certification_leaves_the_original_alone() -> None:
    base = person(certifications=())
    grown = base.with_certification(cert())
    assert not base.certified_on(DAY)
    assert grown.certified_on(DAY)


def test_the_roster_refuses_a_duplicate_badge() -> None:
    roster = Roster.of([person()])
    with pytest.raises(ConflictError):
        roster.with_person(person(name="Someone Else"))


def test_the_roster_finds_and_filters() -> None:
    trainee = person(badge="T-9100", name="A Novak", role=Role.TRAINEE)
    roster = Roster.of([person(), trainee])
    assert roster.get("t 4471").name == "R Ferreira"
    assert [item.badge for item in roster.who_may_release(DAY)] == ["T-4471"]
    with pytest.raises(NotFoundError):
        roster.get("T-0000")


def test_someone_who_has_left_is_not_on_duty() -> None:
    gone = person(badge="T-9200", employed=DateRange(date(2019, 1, 1), date(2024, 6, 1)))
    roster = Roster.of([person(), gone])
    assert [item.badge for item in roster.on_duty(DAY)] == ["T-4471"]


def test_lapsing_within_finds_certifications_about_to_run_out() -> None:
    soon = person(badge="T-9300", certifications=(cert(end=date(2024, 10, 1)),))
    roster = Roster.of([person(), soon])
    assert [item.badge for item in roster.lapsing_within(DAY, 30)] == ["T-9300"]
    assert roster.lapsing_within(DAY, 5) == ()


def test_an_open_ended_certification_never_lapses() -> None:
    forever = person(badge="T-9400", certifications=(cert(end=None),))
    roster = Roster.of([forever])
    assert roster.lapsing_within(DAY, 3650) == ()


def test_lapsing_within_refuses_a_negative_horizon() -> None:
    with pytest.raises(ValidationError):
        Roster.of([person()]).lapsing_within(DAY, -1)


def test_label() -> None:
    assert str(person()) == "T-4471 R Ferreira"
