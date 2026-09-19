"""Host-only platform v1 decoder/normalizer. Not a router JSON implementation.

Validates this specific contract, not arbitrary JSON Schema. ABI grammar validation
is deliberately delegated to nm_validate/nk_parse_feed, not duplicated in Python.
An error must invalidate the active set, not cause a caller to drop a document.
"""
import json
import re


class ManifestInputError(ValueError):
    def __init__(self, code='MANIFEST_INVALID'):
        super().__init__(code)
        self.code = code


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ManifestInputError()
        result[key] = value
    return result


def _keys(value, required, optional=()):
    if not isinstance(value, dict) or not set(required) <= value.keys():
        raise ManifestInputError()
    if value.keys() - set(required) - set(optional):
        raise ManifestInputError()


def _text(value, pattern, limit, empty=False):
    if not isinstance(value, str) or len(value) > limit:
        raise ManifestInputError()
    if not value and not empty:
        raise ManifestInputError()
    if re.fullmatch(pattern, value, flags=re.ASCII) is None:
        raise ManifestInputError()
    return value


def normalize(text):
    """Return the 12 literal arguments to nm_validate, or fail closed.

    The shell validator MUST still accept the returned record before selection.
    This API cannot be used as a substitute for ABI semantic validation.
    """
    try:
        if not isinstance(text, str) or len(text.encode('utf-8')) > 16384:
            raise ManifestInputError()
    except UnicodeError as exc:
        raise ManifestInputError() from exc
    try:
        doc = json.loads(text, object_pairs_hook=_object,
                         parse_constant=lambda _: (_ for _ in ()).throw(ManifestInputError()))
    except (ValueError, RecursionError) as exc:
        if isinstance(exc, ManifestInputError):
            raise
        raise ManifestInputError() from exc
    _keys(doc, ('schema_version', 'document_type', 'id', 'identity'), ('note',))
    if type(doc['schema_version']) is not int:
        raise ManifestInputError()
    if doc['schema_version'] != 1:
        raise ManifestInputError('MANIFEST_SCHEMA_UNSUPPORTED')
    if doc['document_type'] != 'platform':
        raise ManifestInputError()
    ident = doc['identity']
    _keys(ident, ('distribution', 'release', 'revision', 'board_name', 'target',
                  'architecture', 'kernel', 'kernel_abi'))
    rev = ident['revision']
    _keys(rev, ('policy', 'value', 'rationale'))
    if rev['policy'] not in ('exact', 'informational'):
        raise ManifestInputError()
    token = r'[a-zA-Z0-9_.,/+~\-]+'
    identifier = _text(doc['id'], r'[a-zA-Z0-9_.\-]+', 64)
    for field in ('distribution', 'release', 'board_name', 'target', 'architecture', 'kernel'):
        _text(ident[field], token, 128)
    if ident['distribution'] not in ('OpenWrt', 'ImmortalWrt'):
        raise ManifestInputError()
    rationale = _text(rev['rationale'], r'[ -~]*', 256, empty=rev['policy'] == 'exact')
    if rev['value'] is None:
        if rev['policy'] != 'informational':
            raise ManifestInputError()
        revision = '-'
    else:
        revision = _text(rev['value'], token, 128)
        if revision == '-':
            raise ManifestInputError()
    abi = ident['kernel_abi']
    if abi is None:
        abi = '-'
    else:
        _text(abi, token, 60)
        if abi == '-':
            raise ManifestInputError()
    if 'note' in doc:
        _text(doc['note'], r'[ -~]*', 256, empty=True)
    return ['1', identifier, ident['distribution'], ident['release'], rev['policy'],
            revision, rationale, ident['board_name'], ident['target'],
            ident['architecture'], ident['kernel'], abi]
