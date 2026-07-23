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


# YAML 1.2 resolves only canonical true/false as booleans; PyYAML's 1.1 set also
# grabs yes/no/on/off/y/n. Drop the 1.1 bool resolver and re-add a 1.2 one, and
# drop the 1.1-only `=` (value) and timestamp resolvers so those stay strings.
_BOOL_12 = re.compile(r"^(?:true|True|TRUE|false|False|FALSE)$")
_DROP_TAGS = {"tag:yaml.org,2002:bool", "tag:yaml.org,2002:value", "tag:yaml.org,2002:timestamp"}

_resolvers = {}
for ch, mappings in Yaml12Loader.yaml_implicit_resolvers.items():
    _resolvers[ch] = [(tag, rx) for tag, rx in mappings if tag not in _DROP_TAGS]
for ch in "tTfF":
    _resolvers.setdefault(ch, []).append(("tag:yaml.org,2002:bool", _BOOL_12))
Yaml12Loader.yaml_implicit_resolvers = _resolvers


def load_yaml(text):
    return yaml.load(text, Loader=Yaml12Loader)
