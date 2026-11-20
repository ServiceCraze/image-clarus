"""Strict schema parsing and offline validation."""

import json
import math

from jsonschema import (
    Draft3Validator,
    Draft4Validator,
    Draft6Validator,
    Draft7Validator,
    Draft201909Validator,
    Draft202012Validator,
)
from jsonschema.exceptions import SchemaError
from jsonschema.validators import validator_for
from referencing import Registry, Resource
from referencing.exceptions import Unresolvable
from referencing.jsonschema import (
    DRAFT3,
    DRAFT4,
    DRAFT6,
    DRAFT7,
    DRAFT201909,
    DRAFT202012,
    lookup_recursive_ref,
)

from image_clarus.config_errors import ConfigurationError


def _fail():
    raise ConfigurationError("Invalid configuration")


def _strict_json(path):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError
            result[key] = value
        return result

    def invalid_constant(_):
        raise ValueError

    try:
        result = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=pairs,
            parse_constant=invalid_constant,
        )
        pending = [result]
        while pending:
            value = pending.pop()
            if isinstance(value, str):
                value.encode("utf-8")
            elif isinstance(value, float) and not math.isfinite(value):
                raise ValueError
            elif isinstance(value, dict):
                pending.extend(value.keys())
                pending.extend(value.values())
            elif isinstance(value, list):
                pending.extend(value)
        return result
    except (OSError, UnicodeError, ValueError, RecursionError):
        raise ConfigurationError("Invalid selected schema") from None


def _check_schema(path):
    schema = _strict_json(path)
    if (
        not isinstance(schema, dict)
        or schema.get("type") != "object"
        or schema.get("$schema", "https://json-schema.org/draft/2020-12/schema")
        != "https://json-schema.org/draft/2020-12/schema"
    ):
        _fail()

    # Descend uses the caller's specification for scope, then evolves the
    # validator using the child's $schema (including jsonschema's fallback).
    specs = {
        Draft3Validator: DRAFT3,
        Draft4Validator: DRAFT4,
        Draft6Validator: DRAFT6,
        Draft7Validator: DRAFT7,
        Draft201909Validator: DRAFT201909,
        Draft202012Validator: DRAFT202012,
    }

    def children(node, cls):
        maps = {"properties", "patternProperties", "definitions"}
        arrays = (
            {"allOf", "anyOf", "oneOf"} if cls is not Draft3Validator else {"extends"}
        )
        singles = {"additionalProperties", "additionalItems"}
        if cls is not Draft3Validator:
            singles.add("not")
        if cls in (
            Draft6Validator,
            Draft7Validator,
            Draft201909Validator,
            Draft202012Validator,
        ):
            singles.update({"contains", "propertyNames"})
        if cls in (Draft7Validator, Draft201909Validator, Draft202012Validator):
            singles.update({"if", "then", "else"})
        if cls in (Draft201909Validator, Draft202012Validator):
            maps.update({"$defs", "dependentSchemas"})
            singles.update(
                {"contentSchema", "unevaluatedItems", "unevaluatedProperties"}
            )
        if cls is Draft202012Validator:
            arrays.add("prefixItems")
            singles.discard("additionalItems")
        for key in maps:
            value = node.get(key)
            if isinstance(value, dict):
                yield from value.values()
        for key in arrays:
            value = node.get(key)
            if isinstance(value, list):
                yield from value
            elif key == "extends" and isinstance(value, (dict, bool)):
                yield value
        for key in singles | {"items"}:
            value = node.get(key)
            if isinstance(value, (dict, bool)):
                yield value
            elif (
                key == "items"
                and cls is not Draft202012Validator
                and isinstance(value, list)
            ):
                yield from value
        if cls is Draft3Validator:
            # Draft 3 permits schemas as alternatives to named types.
            for key in ("type", "disallow"):
                value = node.get(key)
                for option in value if isinstance(value, list) else (value,):
                    if isinstance(option, dict):
                        yield option
        if cls in (Draft3Validator, Draft4Validator, Draft6Validator, Draft7Validator):
            dependencies = node.get("dependencies")
            if isinstance(dependencies, dict):
                for value in dependencies.values():
                    if isinstance(value, (dict, bool)):
                        yield value

    try:
        Draft202012Validator.check_schema(schema)
        uri = schema.get("$id", "urn:image-clarus:selected-schema")
        registry = Registry().with_resource(
            uri, Resource.from_contents(schema, default_specification=DRAFT202012)
        )
        # A lookup supplies an already-entered resolver; ordinary descent does not.
        pending = [(schema, Draft202012Validator, registry.resolver(uri), True)]
        seen = []
        while pending:
            node, caller, resolver, entered = pending.pop()
            if not isinstance(node, (dict, bool)):
                _fail()
            if not entered:
                resolver = resolver.in_subresource(specs[caller].create_resource(node))
            cls = validator_for(node, default=caller)
            state = (id(node), cls, caller, resolver)
            if state in seen:
                continue
            seen.append(state)
            if isinstance(node, bool):
                continue
            if entered and node is not schema:
                cls.check_schema(node)
            if (node is not schema and "$id" in node) or "$dynamicRef" in node:
                _fail()
            if "$ref" in node:
                ref = node["$ref"]
                if not isinstance(ref, str) or not ref.startswith("#"):
                    _fail()
                resolved = resolver.lookup(ref)
                pending.append((resolved.contents, cls, resolved.resolver, True))
            if cls is Draft201909Validator and "$recursiveRef" in node:
                ref = node["$recursiveRef"]
                if not isinstance(ref, str) or not ref.startswith("#"):
                    _fail()
                # Enforce the same fragment/resolvability policy even though
                # referencing's recursive lookup follows its recursive anchor.
                resolver.lookup(ref)
                resolved = lookup_recursive_ref(resolver)
                pending.append((resolved.contents, cls, resolved.resolver, True))
            pending.extend(
                (child, cls, resolver, False) for child in children(node, cls)
            )
    except (SchemaError, Unresolvable, RecursionError, ValueError, TypeError, KeyError):
        raise ConfigurationError("Invalid selected schema") from None
