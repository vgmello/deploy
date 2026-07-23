"""YAML loading that matches yq's YAML 1.2 scalar rules.

PyYAML's SafeLoader implements YAML 1.1, where ``on``/``off``/``yes``/``no``
(and ``=``, sexagesimals, and 1.1 timestamps) resolve to non-string types.
The manifest layer previously ran through yq (YAML 1.2), where those are plain
strings. We strip the 1.1-only implicit resolvers so a value like
``env: {MODE: on}`` stays the string ``"on"`` instead of becoming ``True``.
"""

import re

import yaml


class Yaml12Loader(yaml.SafeLoader):
    pass


# YAML 1.2 resolves only canonical true/false as booleans and drops the 1.1
# sexagesimal number forms; PyYAML's 1.1 set also grabs yes/no/on/off/y/n as
# bools and 60:30 as an int. Drop the 1.1 bool/int/float resolvers plus the
# 1.1-only `=` (value) and timestamp resolvers, then re-add 1.2-only bool, int,
# and float resolvers (no sexagesimals) so those scalars parse like yq.
_BOOL_12 = re.compile(r"^(?:true|True|TRUE|false|False|FALSE)$")
_INT_12 = re.compile(r"^[-+]?(?:0|[1-9][0-9]*|0o?[0-7]+|0x[0-9a-fA-F]+)$")
_FLOAT_12 = re.compile(
    r"^[-+]?(?:\.[0-9]+|[0-9]+(?:\.[0-9]*)?)(?:[eE][-+]?[0-9]+)?$|^[-+]?\.(?:inf|Inf|INF)$|^\.(?:nan|NaN|NAN)$"
)
_ADD = [
    ("tag:yaml.org,2002:bool", _BOOL_12, "tTfF"),
    ("tag:yaml.org,2002:int", _INT_12, "-+0123456789"),
    ("tag:yaml.org,2002:float", _FLOAT_12, "-+0123456789."),
]
_DROP_TAGS = {
    "tag:yaml.org,2002:bool",
    "tag:yaml.org,2002:int",
    "tag:yaml.org,2002:float",
    "tag:yaml.org,2002:value",
    "tag:yaml.org,2002:timestamp",
}

_resolvers = {}
for ch, mappings in Yaml12Loader.yaml_implicit_resolvers.items():
    _resolvers[ch] = [(tag, rx) for tag, rx in mappings if tag not in _DROP_TAGS]
for tag, regexp, first_chars in _ADD:
    for ch in first_chars:
        _resolvers.setdefault(ch, []).append((tag, regexp))
Yaml12Loader.yaml_implicit_resolvers = _resolvers


def load_yaml(text):
    return yaml.load(text, Loader=Yaml12Loader)
