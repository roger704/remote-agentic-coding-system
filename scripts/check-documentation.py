#!/usr/bin/env python3
"""Vendored from agent-stack. Structural checks and review signals, not semantic proof."""
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

MAX_DOCUMENT_BYTES = 256 * 1024


def git(root, *args):
    result = subprocess.run(['git', '-C', str(root), *args], capture_output=True, text=True)
    if result.returncode:
        raise ValueError('Git metadata unavailable for documentation check')
    return result.stdout.strip()


def safe_file(root, name, config=False, workflow=False):
    if not isinstance(name, str) or len(name) > 240 or not name:
        raise ValueError('Invalid document path')
    parts = name.split('/')
    if any(not p or p in ('.', '..') for p in parts) or '\\' in name:
        raise ValueError('Unsafe document path')
    if config:
        if name != '.nexus/project.json':
            raise ValueError('Unexpected configuration path')
    elif workflow:
        if not re.fullmatch(r'\.github/workflows/[A-Za-z0-9_.-]+\.ya?ml', name):
            raise ValueError('Unexpected workflow path')
    elif any(p.startswith('.') for p in parts) or not re.fullmatch(r'[A-Za-z0-9_./ -]+', name):
        raise ValueError('Unsafe document path')
    candidate = root
    for part in parts:
        candidate = candidate / part
        if candidate.is_symlink():
            raise ValueError('Symlink document paths are forbidden: ' + name)
    if not candidate.is_file() or not candidate.resolve().is_relative_to(root.resolve()):
        raise ValueError('Missing document: ' + name)
    if candidate.stat().st_size > MAX_DOCUMENT_BYTES:
        raise ValueError('Oversized document: ' + name)
    text = candidate.read_text(encoding='utf-8')
    meaningful = re.sub(r'<!--.*?-->', '', text, flags=re.S).strip()
    if len(meaningful) < 40 or meaningful.lower() in ('todo', 'todo: document your project here'):
        raise ValueError('Empty or placeholder document: ' + name)
    return candidate


def doc_path(name):
    return isinstance(name, str) and bool(re.fullmatch(
        r'(?:(?:README|API|ARCHITECTURE|CONTRIBUTING|CHANGELOG)(?:\.[A-Za-z-]+)?\.md|(?:docs|documentation)/.+\.(?:md|mdx|ya?ml|json))', name, re.I))


def read_config(root):
    path = safe_file(root, '.nexus/project.json', config=True)
    config = json.loads(path.read_text())
    if not isinstance(config, dict) or type(config.get('schema_version')) is not int or config.get('schema_version') != 1:
        raise ValueError('Unsupported documentation configuration')
    if set(config) - {'schema_version', 'documentation', 'deployments', 'manual_environments'}:
        raise ValueError('Unknown configuration field')
    docs = config.get('documentation')
    if not isinstance(docs, dict) or set(docs) - {'required', 'api', 'operational_notes'}:
        raise ValueError('Invalid documentation declaration')
    for key, maximum in [('required', 30), ('api', 20), ('operational_notes', 10)]:
        paths = docs.get(key, [])
        if not isinstance(paths, list) or len(paths) > maximum or (key == 'required' and not paths):
            raise ValueError('Invalid documentation list: ' + key)
        if any(not doc_path(x) for x in paths) or len(set(paths)) != len(paths):
            raise ValueError('Invalid or duplicate documentation path: ' + key)
        for name in paths:
            safe_file(root, name)
    safe_file(root, 'changelogs/README.md')
    environments = config.get('manual_environments', [])
    if not isinstance(environments, list) or len(environments) > 20 or any(
            not isinstance(x, str) or not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,49}', x) for x in environments):
        raise ValueError('Invalid manual environments')
    deployments = config.get('deployments', [])
    if not isinstance(deployments, list) or len(deployments) > 20:
        raise ValueError('Invalid deployments')
    for deployment in deployments:
        if not isinstance(deployment, dict) or deployment.get('source') != 'workflow_head':
            raise ValueError('Invalid deployment source binding')
        if not re.fullmatch(r'\.github/workflows/[A-Za-z0-9_.-]+\.ya?ml', str(deployment.get('workflow', ''))):
            raise ValueError('Invalid deployment workflow')
        safe_file(root, deployment['workflow'], workflow=True)
        if not isinstance(deployment.get('job'), str) or not 1 <= len(deployment['job']) <= 150:
            raise ValueError('Invalid deployment job')
        if not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,49}', str(deployment.get('environment', ''))):
            raise ValueError('Invalid deployment environment')
    return config


def check(root, base=None):
    config = read_config(root)
    head = git(root, 'rev-parse', 'HEAD')
    if base is not None:
        if not re.fullmatch(r'[a-f0-9]{40}', base):
            raise ValueError('Comparison base must be an immutable 40-character Git SHA')
        git(root, 'cat-file', '-e', base + '^{commit}')
        changes = git(root, 'diff', '--name-only', base, 'HEAD').splitlines()
    else:
        # Whole-tree signal when there is no known previous deployment/base.
        changes = git(root, 'ls-files').splitlines()
    changed_docs = [p for p in changes if doc_path(p)]
    runtime = [p for p in changes if not doc_path(p) and not p.startswith('changelogs/')]
    api = [p for p in runtime if re.search(r'(^|/)(api|routes?|schemas?|controllers?)(/|\.)|openapi|swagger', p, re.I)]
    migrations = [p for p in runtime if re.search(r'migrat|docker|compose|deploy|requirements|package.*json|\.env', p, re.I)]
    return {'ok': True, 'source_sha': head, 'comparison_base': base,
            'required_documents': config['documentation']['required'],
            'api_documents': config['documentation'].get('api', []),
            'documentation_changed': changed_docs[:100],
            'documentation_review_required': bool(runtime),
            'api_review_required': bool(api), 'operational_review_required': bool(migrations),
            'changed_non_documentation_paths': runtime[:100], 'changed_api_paths': api[:100],
            'changed_operational_paths': migrations[:100],
            'changed_path_count': len(changes),
            'path_lists_truncated': any(len(paths) > 100 for paths in [runtime, api, migrations, changed_docs]),
            'limitation': 'Structural validation and change signals do not prove documentation is semantically current. Review flagged changes before deployment.'}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path.cwd())
    parser.add_argument('--base', help='Known previous source/base commit SHA; omitted means whole-tree review signal')
    args = parser.parse_args(argv)
    try:
        print(json.dumps(check(args.root.resolve(), args.base), indent=2))
        return 0
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        print(json.dumps({'ok': False, 'error': str(exc)}), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
