from cloudapp.yamlcompat import load_yaml


def test_yaml_11_boolean_words_stay_strings():
    # yq (YAML 1.2) keeps these as strings; PyYAML's default 1.1 loader would
    # coerce them to booleans and break schema validation of env maps.
    doc = load_yaml("env:\n  DEBUG: on\n  MODE: no\n  FLAG: yes\n")
    assert doc["env"] == {"DEBUG": "on", "MODE": "no", "FLAG": "yes"}


def test_canonical_booleans_still_parse():
    assert load_yaml("a: true\nb: false\n") == {"a": True, "b": False}


def test_numbers_and_null_unchanged():
    doc = load_yaml("port: 8080\nratio: 0.5\nnothing: null\n")
    assert doc == {"port": 8080, "ratio": 0.5, "nothing": None}


def test_sexagesimal_stays_string():
    # YAML 1.1 parses 60:30 as 3630 (base-60); yq / YAML 1.2 keeps it a string.
    assert load_yaml("v: 60:30\n") == {"v": "60:30"}


def test_int_and_float_forms_still_parse():
    doc = load_yaml("a: 8080\nb: -3\nc: 0x1F\nd: 1.5e3\ne: .inf\n")
    assert doc["a"] == 8080 and doc["b"] == -3 and doc["c"] == 31
    assert doc["d"] == 1500.0 and doc["e"] == float("inf")
