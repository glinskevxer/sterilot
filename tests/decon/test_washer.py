from __future__ import annotations

from datetime import date

import pytest

from sterilot.decon.washer import Washer, WasherClass
from sterilot.errors import ValidationError
from sterilot.interval import DateRange

DAY = date(2024, 5, 1)


def washer(**changes: object) -> Washer:
    values: dict[str, object] = {
        "equipment": "wd 2",
        "model": "Reliance 444",
        "manufacturer": "Steris",
        "last_qualification": date(2024, 1, 10),
    }
    values.update(changes)
    return Washer(**values)  # type: ignore[arg-type]


def test_class_lookup_and_labels() -> None:
    assert WasherClass.named("cart washer") is WasherClass.CART_WASHER
    assert WasherClass.named("SINGLE-CHAMBER") is WasherClass.SINGLE_CHAMBER
    assert WasherClass.TUNNEL.label == "tunnel"
    with pytest.raises(ValidationError):
        WasherClass.named("dishwasher")


def test_only_chamber_machines_disinfect() -> None:
    assert WasherClass.SINGLE_CHAMBER.disinfects
    assert WasherClass.TUNNEL.disinfects
    assert not WasherClass.ULTRASONIC.disinfects
    assert not WasherClass.CART_WASHER.disinfects


def test_a_cart_washer_does_not_take_instruments() -> None:
    assert not WasherClass.CART_WASHER.takes_instruments
    assert WasherClass.ULTRASONIC.takes_instruments


def test_equipment_id_is_normalised_and_details_required() -> None:
    assert washer().equipment == "WD-2"
    with pytest.raises(ValidationError):
        washer(model="")
    with pytest.raises(ValidationError):
        washer(manufacturer=" ")


def test_a_washer_has_at_least_one_chamber() -> None:
    with pytest.raises(ValidationError):
        washer(chambers=0)


def test_only_a_tunnel_has_several_chambers() -> None:
    with pytest.raises(ValidationError):
        washer(chambers=4)
    assert washer(chambers=4, washer_class=WasherClass.TUNNEL).chambers == 4


def test_a_machine_with_no_window_is_always_in_service() -> None:
    assert washer().in_service_on(date(2030, 1, 1))


def test_a_retired_machine_is_refused() -> None:
    item = washer(in_service=DateRange(date(2019, 1, 1), date(2024, 1, 1)))
    assert item.refusal_on(DAY) == "the machine is not in service"


def test_an_out_of_order_machine_is_refused_first() -> None:
    item = washer(out_of_order=True, last_qualification=None)
    assert item.refusal_on(DAY) == "the machine is out of order"


def test_qualification_falls_due_after_a_year() -> None:
    assert not washer().qualification_due(DAY)
    assert washer(last_qualification=date(2023, 1, 1)).qualification_due(DAY)
    assert washer(last_qualification=None).qualification_due(DAY)


def test_days_to_qualification_counts_down() -> None:
    item = washer(last_qualification=date(2024, 1, 10))
    assert item.days_to_qualification(DAY) == 253
    assert washer(last_qualification=None).days_to_qualification(DAY) is None


def test_a_machine_past_qualification_cannot_run() -> None:
    item = washer(last_qualification=date(2022, 1, 1))
    assert not item.usable_on(DAY)
    assert item.refusal_on(DAY) == "the machine is past its qualification date"


def test_a_healthy_machine_runs() -> None:
    assert washer().usable_on(DAY)
    assert washer().refusal_on(DAY) is None


def test_an_ultrasonic_may_run_but_may_not_finish_an_instrument() -> None:
    item = washer(washer_class=WasherClass.ULTRASONIC)
    assert item.usable_on(DAY)
    assert item.may_finish_instruments(DAY) == "the machine does not run a thermal rinse"


def test_a_cart_washer_is_refused_for_instruments_by_name() -> None:
    item = washer(washer_class=WasherClass.CART_WASHER)
    assert item.may_finish_instruments(DAY) == "a cart washer does not process instruments"


def test_a_broken_chamber_machine_reports_the_machine_fault_first() -> None:
    item = washer(out_of_order=True)
    assert item.may_finish_instruments(DAY) == "the machine is out of order"


def test_a_healthy_chamber_machine_may_finish_instruments() -> None:
    assert washer().may_finish_instruments(DAY) is None


def test_qualifying_resets_the_clock() -> None:
    item = washer(last_qualification=date(2022, 1, 1)).qualified(DAY)
    assert item.last_qualification == DAY
    assert item.usable_on(DAY)


def test_label() -> None:
    assert str(washer()) == "WD-2 Reliance 444"
