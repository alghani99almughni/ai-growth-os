"""Booking scenarios, run through the real /call and /voice/turn endpoints.

* every scenario runs on the default tenant profile;
* scenarios flagged smoke=True also run on EVERY other tenant profile (other industries, time zones, opening hours and
  weekly closures), which is how we prove the behaviour applies to all tenants by default, not just one configuration.

No AI provider is configured in tests, so nothing here can spend tokens or touch the network.
"""
import pytest

from booking_engine import DEFAULT, PROFILES, Harness, run_scenario
from booking_scenarios import SCENARIOS


def _cases():
    for sc in SCENARIOS:
        yield pytest.param(sc, DEFAULT, id=f"{sc.id}@{DEFAULT.name}")
        if sc.smoke:
            for profile in PROFILES:
                if profile is DEFAULT:
                    continue
                if sc.needs_closed_day and not profile.closed:
                    continue          # e.g. a restaurant open every day has no closed day to talk about
                yield pytest.param(sc, profile, id=f"{sc.id}@{profile.name}")


@pytest.fixture(scope="module")
def harness():
    return Harness()


@pytest.mark.parametrize("sc,profile", list(_cases()))
def test_booking_scenario(harness, sc, profile):
    if sc.xfail:
        pytest.xfail(sc.xfail)
    run_scenario(harness, sc, profile)


def test_scenario_ids_are_unique():
    ids = [s.id for s in SCENARIOS]
    assert len(ids) == len(set(ids))


def test_there_are_scenarios_for_every_part_of_the_booking_journey():
    categories = {s.category.split(". ", 1)[1] for s in SCENARIOS}
    assert {"Starting a booking", "Choosing the day", "Giving the time", "Confirming, declining and changing",
            "Two callers, one slot", "Cancelling, rescheduling and checking", "Choosing a service",
            "After the booking", "Messy real-world speech", "Other languages"} <= categories
    assert len(SCENARIOS) >= 90
