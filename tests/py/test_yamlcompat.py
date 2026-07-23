from cloudtool.yamlcompat import load_yaml


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
