import itertools

import numpy as np
import pytest

from nestra.fuzzy import FuzzyVariable, MamdaniSystem, rule, trapmf, trimf
from nestra.fuzzy.rules import AC_COMFORT, FAN_COMFORT, LIGHT_COMFORT, SYSTEMS


def test_trimf_shape():
    mf = trimf(0, 5, 10)
    assert float(mf(0)) == 0
    assert float(mf(2.5)) == pytest.approx(0.5)
    assert float(mf(5)) == 1
    assert float(mf(10)) == 0


def test_shoulders():
    left = trapmf(0, 0, 2, 4)
    right = trapmf(6, 8, 10, 10)
    assert float(left(0)) == 1
    assert float(right(10)) == 1


def test_rule_parsing_and_description():
    r = rule("temperature is very hot and humidity is not humid", "max")
    assert [str(c) for c in r.clauses] == ["temperature is very hot", "humidity is not humid"]
    assert r.describe("fan_speed") == "IF temperature is very hot AND humidity is not humid THEN fan_speed is max"


def test_invalid_rules_are_rejected():
    with pytest.raises(ValueError):
        rule("a is b and c is d or e is f", "x")
    var = FuzzyVariable("x", 0, 1, {"lo": trimf(0, 0, 1)})
    with pytest.raises(ValueError):
        MamdaniSystem("bad", [var], var, [rule("x is missing", "lo")])


def test_term_value_is_centroid():
    var = FuzzyVariable("v", 0, 100, {"mid": trimf(40, 50, 60)})
    assert var.term_value("mid") == pytest.approx(50, abs=0.1)


def test_inference_returns_explanation():
    result = FAN_COMFORT.infer(temperature=29, humidity=70)
    assert result.term == "high"
    assert result.activations and result.activations[0].strength > 0
    assert "fan_speed" in result.activations[0].rule


def test_fan_gets_faster_as_it_gets_hotter():
    speeds = [FAN_COMFORT.infer(temperature=t, humidity=60).value for t in (18, 23, 27, 31, 36)]
    assert speeds == sorted(speeds)
    assert speeds[0] < 10 and speeds[-1] > 80


def test_ac_targets_warmer_at_night():
    day = AC_COMFORT.infer(temperature=28, humidity=55, time_of_day=14).value
    night = AC_COMFORT.infer(temperature=28, humidity=55, time_of_day=23.5).value
    assert 23 <= day <= 26
    assert night > day


def test_lights_dimmer_in_daylight():
    daylight = LIGHT_COMFORT.infer(time_of_day=13, ambient_light=90).value
    dark_morning = LIGHT_COMFORT.infer(time_of_day=7, ambient_light=5).value
    assert daylight < dark_morning


@pytest.mark.parametrize("name", list(SYSTEMS))
def test_rule_bases_cover_the_whole_input_space(name):
    """Some rule must fire for any input, otherwise inference fails at runtime."""
    system = SYSTEMS[name]
    grids = [np.linspace(v.lo, v.hi, 13) for v in system.inputs.values()]
    for combo in itertools.product(*grids):
        system.infer(**dict(zip(system.inputs, combo)))
