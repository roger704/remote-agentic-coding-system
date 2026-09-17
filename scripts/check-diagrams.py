#!/usr/bin/env python3
"""Source-bound diagram review receipts; canonical copy in agent-stack."""
import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit

MANIFEST = '.nexus/diagrams.json'
DOCUMENT = re.compile(r'^docs/diagrams/(?:[A-Za-z0-9_-]+/)*[A-Za-z0-9_.-]+\.md$')
def mermaid_blocks(text):
    blocks, body, fence = [], [], None
    for line in text.splitlines():
        if fence is None:
            opening = re.match(r'^ {0,3}(`{3,}|~{3,})mermaid\s*$', line, re.I)
            if opening:
                fence, body = opening.group(1), []
        elif re.fullmatch(r' {0,3}' + re.escape(fence[0]) + '{' + str(len(fence)) + r',}\s*', line):
            blocks.append('\n'.join(body))
            fence = None
        else:
            body.append(line)
    if fence is not None:
        raise ValueError('Unterminated Mermaid diagram')
    return blocks


def git(root, *args):
    result = subprocess.run(['git', '-C', str(root), *args], capture_output=True)
    if result.returncode:
        raise ValueError('Git source inventory unavailable')
    return result.stdout


def fingerprint(root, index=False):
    rows = []
    for record in git(root, *(['ls-files', '--stage', '-z'] if index else ['ls-tree', '-r', '-z', 'HEAD'])).split(b'\0'):
        if not record:
            continue
        meta, path = record.split(b'\t', 1)
        parts = meta.decode('ascii').split()
        if index:
            mode, sha, stage = parts
            if stage != '0':
                raise ValueError('Resolve merge conflicts before reviewing diagrams')
            kind = 'commit' if mode == '160000' else 'blob'
        else:
            mode, kind, sha = parts
        if path == MANIFEST.encode() or path.startswith((b'docs/diagrams/', b'changelogs/')):
            continue
        rows.append((path, mode, kind, sha))
    if not rows:
        raise ValueError('Empty source inventory')
    digest = hashlib.sha256()
    for path, mode, kind, sha in sorted(rows, key=lambda row: row[0]):
        digest.update(path + b'\0' + mode.encode() + b'\0' + kind.encode() + b'\0' + sha.encode() + b'\n')
    return digest.hexdigest()


def safe_file(root, relative):
    path = root
    for part in Path(relative).parts:
        path = path / part
        if path.is_symlink():
            raise ValueError('Diagram files and directories cannot be symlinks')
    if not path.is_file() or not path.resolve().is_relative_to(root.resolve()):
        raise ValueError('Missing or unsafe diagram file: ' + relative)
    if path.stat().st_size > 128 * 1024:
        raise ValueError('Diagram file exceeds 128 KiB: ' + relative)
    return path


def manifest(root):
    value = json.loads(safe_file(root, MANIFEST).read_text())
    if not isinstance(value, dict) or set(value) != {'schema_version', 'documents', 'source_fingerprint'}:
        raise ValueError('Invalid diagram manifest fields')
    if type(value['schema_version']) is not int or value['schema_version'] != 1:
        raise ValueError('Unsupported diagram manifest version')
    docs = value['documents']
    if not isinstance(docs, list) or not 1 <= len(docs) <= 10 or any(not isinstance(p, str) or not DOCUMENT.fullmatch(p) or any(x.startswith('.') for x in p.split('/')) for p in docs):
        raise ValueError('Invalid diagram document paths')
    if len(set(docs)) != len(docs) or not isinstance(value['source_fingerprint'], str) or not re.fullmatch('[a-f0-9]{64}', value['source_fingerprint']):
        raise ValueError('Invalid diagram fingerprint or duplicate documents')
    return value


def inspect_documents(root, value):
    count = 0
    for name in value['documents']:
        text = safe_file(root, name).read_text()
        blocks = mermaid_blocks(text)
        if not blocks:
            raise ValueError('Each diagram document needs a current architecture or flow view: ' + name)
        if len(blocks) > 20 or any(len(block) > 32000 for block in blocks):
            raise ValueError('Diagram complexity exceeds validation budget')
        for block in blocks:
            if not re.match(r'\s*(?:flowchart|graph|sequenceDiagram|stateDiagram-v2|classDiagram|erDiagram)\b', block):
                raise ValueError('Unsupported diagram kind: ' + name)
            if '%%{' in block or re.search(r'^\s*click\s|<script|javascript:', block, re.I | re.M):
                raise ValueError('Executable links or Mermaid configuration directives forbidden')
        for raw in re.findall(r'\[[^\]]+\]\(([^)]+)\)', text):
            target = raw.strip().strip('<>')
            parsed = urlsplit(target)
            if parsed.scheme or parsed.netloc or not parsed.path:
                continue
            path = (root / name).parent / unquote(parsed.path)
            if not path.resolve().is_relative_to(root.resolve()) or not path.exists():
                raise ValueError('Broken or escaping diagram evidence link in ' + name)
        count += len(blocks)
    return count


def check(root, index=False, write=False):
    value = manifest(root)
    count = inspect_documents(root, value)
    actual = fingerprint(root, index=index)
    if write:
        value['source_fingerprint'] = actual
        (root / MANIFEST).write_text(json.dumps(value, indent=2) + '\n')
    elif value['source_fingerprint'] != actual:
        raise ValueError('Diagrams need source review. Review/update views, stage source changes, then run python3 scripts/check-diagrams.py --stamp --index and stage .nexus/diagrams.json')
    return {'ok': True, 'documents': value['documents'], 'diagram_count': count, 'source_fingerprint': actual,
            'source': 'index' if index else 'HEAD', 'limitation': 'A review receipt detects source drift; it is not proof of semantic accuracy. Mermaid syntax is checked separately in CI.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path.cwd())
    parser.add_argument('--index', action='store_true', help='Use staged source inventory')
    parser.add_argument('--stamp', action='store_true', help='Record source review only after actually reviewing diagrams')
    args = parser.parse_args()
    if args.stamp and not args.index:
        parser.error('--stamp requires --index so staged source changes are included')
    try:
        print(json.dumps(check(args.root.resolve(), args.index, args.stamp), indent=2))
    except (ValueError, OSError, UnicodeError) as exc:
        print(json.dumps({'ok': False, 'error': str(exc)}), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
