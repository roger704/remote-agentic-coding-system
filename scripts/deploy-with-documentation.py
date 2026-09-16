#!/usr/bin/env python3
"""Run a manual deployment with preflight documentation and a durable Nexus receipt."""
import argparse
from datetime import datetime, timezone
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid

sys.dont_write_bytecode = True
ENDPOINT = 'https://agent.sicken.work/nexus/api/projects/deployments'
TOKEN_NAME = 'NEXUS_DEPLOYMENT_REPORT_TOKEN'


def load_gate():
    spec = importlib.util.spec_from_file_location('documentation_gate', Path(__file__).with_name('check-documentation.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError('Deployment report redirect refused')


def send_report(body, token):
    request = urllib.request.Request(ENDPOINT, data=json.dumps(body).encode(), method='POST',
        headers={'Content-Type': 'application/json', 'x-nexus-deployment-token': token})
    try:
        with urllib.request.build_opener(NoRedirect).open(request, timeout=30) as response:
            # The service may accept asynchronously; this reports acceptance, not persistence.
            if not 200 <= response.status < 300:
                raise ValueError('Deployment report rejected')
            response.read(65536)
    except (urllib.error.URLError, ValueError, OSError):
        # Never print provider response bodies, headers, tokens, or request contents.
        raise ValueError('Nexus report unavailable or rejected; receipt retained locally') from None


def outbox(root, gate):
    path = Path(gate.git(root, 'rev-parse', '--git-path', 'nexus-deployment-outbox'))
    if not path.is_absolute():
        path = root / path
    if path.is_symlink():
        raise ValueError('Outbox must not be a symlink')
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    return path


def save(path, record):
    if path.is_symlink():
        raise ValueError('Receipt must not be a symlink')
    temporary = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, 'w') as file:
            json.dump(record, file, indent=2)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if temporary.exists():
            temporary.unlink()


def repository(root, gate):
    remote = gate.git(root, 'remote', 'get-url', 'origin')
    match = re.fullmatch(r'(?:https://github\.com/|git@github\.com:)([A-Za-z0-9-]+/[A-Za-z0-9_.-]+?)(?:\.git)?', remote)
    if not match:
        raise ValueError('Origin must identify the enrolled GitHub repository')
    return match.group(1)


def validate_evidence(url):
    parsed = urllib.parse.urlsplit(url)
    if len(url) > 2000 or parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError('Evidence URL must be HTTPS without embedded credentials')


def deliver(path, record, token, sender):
    sender(record['body'], token)
    record['state'] = 'accepted'
    save(path, record)
    print(json.dumps({'deployment_id': record['body']['deployment_id'], 'report': 'accepted',
                      'outcome': record['body']['outcome'], 'receipt': str(path)}))


def main(argv=None, sender=send_report):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path.cwd())
    sub = parser.add_subparsers(dest='action', required=True)
    run = sub.add_parser('run')
    run.add_argument('--environment', required=True)
    run.add_argument('--evidence-url', required=True)
    run.add_argument('--operational-notes', required=True)
    run.add_argument('--base', help='Previous deployed source SHA for documentation impact review')
    run.add_argument('command', nargs=argparse.REMAINDER)
    replay = sub.add_parser('replay')
    replay.add_argument('deployment_id')
    args = parser.parse_args(argv)
    try:
        root = args.root.resolve()
        gate = load_gate()
        token = os.environ.get(TOKEN_NAME)
        if not token:
            raise ValueError(TOKEN_NAME + ' must be configured before deployment/report replay')
        if args.action == 'replay':
            if not re.fullmatch(r'[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}', args.deployment_id):
                raise ValueError('Invalid receipt ID')
            path = outbox(root, gate) / (args.deployment_id + '.json')
            if path.is_symlink() or path.stat().st_size > 16384:
                raise ValueError('Unsafe receipt')
            record = json.loads(path.read_text())
            if record.get('state') == 'accepted':
                print('Receipt was already accepted; deployment was not rerun.')
                return 0
            if record.get('state') != 'pending':
                raise ValueError('Incomplete deployment: reconcile actual outcome manually; replay cannot guess success')
            if record['body']['repository'] != repository(root, gate) or record['body']['deployment_id'] != args.deployment_id:
                raise ValueError('Receipt does not match this repository/deployment')
            deliver(path, record, token, sender)
            return 0
        command = args.command[1:] if args.command[:1] == ['--'] else args.command
        if not command:
            raise ValueError('Deployment command argv is required after --')
        if not args.operational_notes.strip() or len(args.operational_notes) > 4000:
            raise ValueError('Operational notes must contain 1 to 4000 characters')
        validate_evidence(args.evidence_url)
        if gate.git(root, 'status', '--porcelain', '--untracked-files=all'):
            raise ValueError('Deployment requires a clean tracked and untracked working tree')
        config = gate.read_config(root)
        if args.environment not in config.get('manual_environments', []):
            raise ValueError('Manual environment is not enrolled in .nexus/project.json')
        report = gate.check(root, args.base)
        print(json.dumps(report, indent=2), flush=True)
        source_sha = report['source_sha']
        if not re.fullmatch(r'[a-f0-9]{40}', source_sha):
            raise ValueError('Deployment source must be an immutable Git SHA')
        deployment_id = str(uuid.uuid4())
        body = {'repository': repository(root, gate), 'environment': args.environment,
                'source_sha': source_sha, 'deployment_id': deployment_id,
                'evidence_url': args.evidence_url, 'operational_notes': args.operational_notes}
        path = outbox(root, gate) / (deployment_id + '.json')
        record = {'state': 'running', 'body': body}
        save(path, record)  # A killed wrapper cannot become a fabricated success on replay.
        child_env = {k: v for k, v in os.environ.items() if k != TOKEN_NAME}
        try:
            result = subprocess.run(command, cwd=root, env=child_env, shell=False)
            exit_code = result.returncode
        except KeyboardInterrupt:
            exit_code = 130
        except OSError:
            exit_code = 127
        if gate.git(root, 'rev-parse', 'HEAD') != source_sha or gate.git(root, 'diff', '--name-only', source_sha):
            # A command that changes checked-out source cannot substantiate this source receipt.
            exit_code = exit_code or 1
            body['operational_notes'] = ('Source checkout changed during command; exact deployed source requires reconciliation. ' + body['operational_notes'])[:4000]
        body['completed_at'] = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
        body['outcome'] = 'success' if exit_code == 0 else 'failure'
        record['state'] = 'pending'
        save(path, record)
        print(json.dumps({'deployment_id': deployment_id, 'receipt': str(path), 'outcome': body['outcome']}))
        deliver(path, record, token, sender)
        return 0 if exit_code == 0 else min(abs(exit_code), 125)
    except (ValueError, OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
        print(str(exc), file=sys.stderr)
        return 3


if __name__ == '__main__':
    raise SystemExit(main())
