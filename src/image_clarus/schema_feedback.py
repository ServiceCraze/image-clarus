"""Normalize schema validation errors independently of pipeline stages."""

from urllib.parse import unquote


def _pointer(parts):
    return "".join("/" + str(x).replace("~", "~0").replace("/", "~1") for x in parts)


def _schema_nodes(root):
    """Index every subschema object of the document to its true pointer."""
    nodes = {}

    def walk(node, tokens):
        if isinstance(node, dict):
            nodes.setdefault(id(node), tokens)
            for key, value in node.items():
                walk(value, tokens + (key,))
        elif isinstance(node, list):
            for position, value in enumerate(node):
                walk(value, tokens + (position,))

    walk(root, ())
    return nodes


def _anchor_pointer(root, anchor):
    """Locate the subschema declaring an $anchor."""
    pending = [((), root)]
    while pending:
        tokens, node = pending.pop()
        if isinstance(node, dict):
            if node.get("$anchor") == anchor:
                return tokens
            pending.extend((tokens + (key,), value) for key, value in node.items())
        elif isinstance(node, list):
            pending.extend(
                (tokens + (position,), value) for position, value in enumerate(node)
            )
    return None


def _resolve_ref(root, ref):
    """Resolve a same-document reference to (pointer tokens, subschema)."""
    seen = set()
    while isinstance(ref, str) and ref not in seen:
        seen.add(ref)
        ref = unquote(ref)
        if ref == "#":
            tokens, node = (), root
        elif ref.startswith("#/"):
            tokens = tuple(
                token.replace("~1", "/").replace("~0", "~")
                for token in ref[2:].split("/")
            )
            node = root
            for token in tokens:
                if isinstance(node, dict) and token in node:
                    node = node[token]
                elif isinstance(node, list) and token.isdigit():
                    node = node[int(token)]
                else:
                    return None
        else:
            tokens = _anchor_pointer(root, ref[1:])
            if tokens is None:
                return None
            node = root
            for token in tokens:
                node = node[token]
        if isinstance(node, dict) and "$ref" in node:
            ref = node["$ref"]
            continue
        return tokens, node
    return None


def _schema_pointer(schema, nodes, error):
    """Actual RFC 6901 pointer to the subschema that reported the error.

    jsonschema's absolute_schema_path records the referring side of every
    $ref it crossed (the $ref keyword itself is never appended), so that
    path alone can name a location that does not exist in the document.
    The failing keyword always sits under error.schema, the real subschema
    object from the document, so anchor the reported keyword there.
    """
    if hasattr(error, "_actual_boolean_schema_path"):
        return _pointer(error._actual_boolean_schema_path)
    reported = tuple(error.absolute_schema_path)
    tokens = nodes.get(id(error.schema))
    if tokens is not None and reported:
        keyword = error.validator
        if isinstance(error.schema, dict) and keyword in error.schema:
            return _pointer(tokens + (keyword,))
        return _pointer(tokens + (reported[-1],))
    # Boolean subschemas have no addressable object identity: replay the
    # reported walk, following local references as jsonschema did.
    node, walked = schema, ()
    for token in reported:
        if isinstance(node, dict) and token in node:
            walked, node = walked + (token,), node[token]
        else:
            return _pointer(reported)
    if isinstance(node, dict) and "$ref" in node:
        resolved = _resolve_ref(schema, node["$ref"])
        if resolved is not None and resolved[1] is error.schema:
            return _pointer(resolved[0])
    return _pointer(reported)


def _feedback(schema, errors):
    nodes = _schema_nodes(schema)
    entries = sorted(
        {
            (
                _pointer(e.absolute_path),
                _schema_pointer(schema, nodes, e),
                str(e.validator),
            )
            for e in errors
        }
    )
    return {
        "kind": "schema_validation",
        "total_errors": len(entries),
        "truncated": len(entries) > 20,
        "errors": [
            {"instance_path": a, "schema_path": b, "keyword": c}
            for a, b, c in entries[:20]
        ],
    }
