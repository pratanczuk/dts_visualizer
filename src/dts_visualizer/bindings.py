from __future__ import annotations
import os
import re
from typing import Dict, Set, Any, List
import yaml


class BindingsIndex:
    def __init__(self):
        # Map compatible -> set of property names that are phandle or phandle-array
        self.compat_to_phandle_props: Dict[str, Set[str]] = {}

    def may_reference_phandle(self, node_compat: str | None, prop: str) -> bool:
        if not node_compat:
            return False
        props = self.compat_to_phandle_props.get(node_compat)
        if not props:
            return False
        # direct match or pinctrl-N style
        if prop in props:
            return True
        if prop.startswith("pinctrl-") and any(p.startswith("pinctrl-") for p in props):
            return True
        return False


def load_bindings(dir_path: str) -> BindingsIndex:
    idx = BindingsIndex()
    for root, _dirs, files in os.walk(dir_path):
        for fn in files:
            if not fn.endswith(('.yaml', '.yml')):
                continue
            path = os.path.join(root, fn)
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    data = yaml.safe_load(f)
            except Exception:
                continue
            if not isinstance(data, dict):
                continue
            # collect compatibles from 'compatible' (const/enum/oneOf forms)
            compatibles = _extract_compatibles(data.get('compatible'))
            if not compatibles:
                continue
            # Identify properties that reference phandles
            phandle_props = _extract_phandle_props(data)
            if not phandle_props:
                continue
            for comp in compatibles:
                s = idx.compat_to_phandle_props.setdefault(comp, set())
                s.update(phandle_props)
    return idx


def _extract_compatibles(compatible_section: Any) -> List[str]:
    res: List[str] = []
    if not compatible_section:
        return res
    if isinstance(compatible_section, dict):
        if 'const' in compatible_section:
            v = compatible_section['const']
            if isinstance(v, str):
                res.append(v)
        if 'enum' in compatible_section and isinstance(compatible_section['enum'], list):
            res += [x for x in compatible_section['enum'] if isinstance(x, str)]
        # Some bindings use oneOf with const/enum
        for key in ('oneOf', 'anyOf', 'allOf'):
            if key in compatible_section and isinstance(compatible_section[key], list):
                for alt in compatible_section[key]:
                    res += _extract_compatibles(alt)
    return list(dict.fromkeys(res))


def _extract_phandle_props(d: dict) -> Set[str]:
    props = d.get('properties')
    result: Set[str] = set()
    if isinstance(props, dict):
        for name, schema in props.items():
            if _schema_is_phandle(schema):
                result.add(name)
    # Also check patternProperties for pinctrl-\d+ etc.
    patt = d.get('patternProperties')
    if isinstance(patt, dict):
        for pat, schema in patt.items():
            if _schema_is_phandle(schema):
                # store the pattern; we'll treat any prop starting with this prefix as eligible
                # For simplicity, store 'pinctrl-' wildcard
                if pat.startswith('^pinctrl-'):
                    result.add('pinctrl-')
    return result


def _schema_is_phandle(schema: Any) -> bool:
    if not isinstance(schema, dict):
        return False
    # direct $ref to phandle/phandle-array
    ref = schema.get('$ref')
    if isinstance(ref, str) and ('/phandle' in ref):
        return True
    # items -> $ref pattern for arrays
    items = schema.get('items')
    if isinstance(items, dict):
        if isinstance(items.get('$ref'), str) and ('/phandle' in items['$ref']):
            return True
    # oneOf/anyOf nesting
    for key in ('oneOf', 'anyOf', 'allOf'):
        arr = schema.get(key)
        if isinstance(arr, list) and any(_schema_is_phandle(x) for x in arr):
            return True
    return False
