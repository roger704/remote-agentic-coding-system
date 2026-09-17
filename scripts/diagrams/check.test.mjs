import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, mkdir, writeFile, rm, symlink, copyFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { validateRepository } from './check.mjs';

async function fixture(t, markdown, documents = ['docs/diagrams/README.md']) {
  const root = await mkdtemp(path.join(tmpdir(), 'diagram-parser-'));
  t.after(() => rm(root, { recursive: true, force: true }));
  await mkdir(path.join(root, '.nexus'));
  await mkdir(path.join(root, 'docs/diagrams'), { recursive: true });
  await writeFile(path.join(root, '.nexus/diagrams.json'), JSON.stringify({ schema_version: 1, documents, source_fingerprint: '0'.repeat(64) }));
  await writeFile(path.join(root, 'docs/diagrams/README.md'), markdown);
  return root;
}
test('parses real flowchart and sequence syntax', async t => {
  const root = await fixture(t, '```mermaid\nflowchart LR\n A[Client] --> B[Gateway]\n```\n```mermaid\nsequenceDiagram\n A->>B: Request\n```');
  assert.deepEqual(await validateRepository(root), { ok: true, documents: 1, diagrams: 2 });
});
test('rejects malformed syntax without returning private document text', async t => {
  const root = await fixture(t, '```mermaid\nflowchart LR\n A[PRIVATE_SENTINEL\n```\n```mermaid\nflowchart LR\n A-->B\n```');
  await assert.rejects(validateRepository(root), error => error.message === 'invalid_mermaid:docs/diagrams/README.md:diagram_1');
});
test('rejects unsafe manifest paths before reading documents', async t => {
  const root = await fixture(t, '', ['../private.md']);
  await assert.rejects(validateRepository(root), /invalid_diagram_manifest/);
});
test('rejects symlink escaping repository', async t => {
  const root = await fixture(t, 'unused');
  await symlink(path.join(root, 'docs/diagrams/README.md'), path.join(root, 'docs/diagrams/link.md'));
  const sibling = await fixture(t, '', ['docs/diagrams/link.md']);
  await symlink(path.join(root, 'docs/diagrams/README.md'), path.join(sibling, 'docs/diagrams/link.md'));
  await assert.rejects(validateRepository(sibling), /symlink_forbidden/);
});
test('rejects missing and unterminated diagram fences', async t => {
  await assert.rejects(validateRepository(await fixture(t, '# No diagram')), /missing_mermaid/);
  await assert.rejects(validateRepository(await fixture(t, '```mermaid\nflowchart LR\n A-->B')), /unterminated_mermaid/);
});

const valid = '```mermaid\nflowchart LR\n A-->B\n```\n```mermaid\nsequenceDiagram\n A->>B: Request\n```';
test('rejects internal document and manifest symlinks', async t => {
  const root = await fixture(t, valid);
  await copyFile(path.join(root, '.nexus/diagrams.json'), path.join(root, '.nexus/copy.json'));
  await rm(path.join(root, '.nexus/diagrams.json'));
  await symlink('copy.json', path.join(root, '.nexus/diagrams.json'));
  await assert.rejects(validateRepository(root), /symlink_forbidden/);
});
test('rejects exact-schema, fingerprint, document count and path violations', async t => {
  const root = await fixture(t, valid);
  const base = {schema_version:1, documents:['docs/diagrams/README.md'], source_fingerprint:'0'.repeat(64)};
  for (const override of [{extra:true}, {schema_version:true}, {source_fingerprint:'bad'}, {documents:Array.from({length:11},(_,i)=>`docs/diagrams/d${i}.md`)}, {documents:['docs/diagrams/with space.md']}, {documents:['docs/diagrams/README.md','docs/diagrams/README.md']}]) {
    await writeFile(path.join(root,'.nexus/diagrams.json'),JSON.stringify({...base,...override}));
    await assert.rejects(validateRepository(root), /invalid_diagram_manifest/);
  }
});
test('rejects active directives, unsupported kinds and complexity limits', async t => {
  for(const value of ['%%{init: {}}%%', 'click A "https://example.com"', '<script>bad</script>', 'javascript:bad']) {
    const root=await fixture(t,valid.replace(' A-->B',` A-->B\n ${value}`));
    await assert.rejects(validateRepository(root),/active_directive_forbidden/);
  }
  await assert.rejects(validateRepository(await fixture(t,valid.replace('flowchart LR','pie'))),/unsupported_diagram_kind/);
  await assert.rejects(validateRepository(await fixture(t,('```mermaid\nflowchart LR\n A-->B\n```\n').repeat(21))),/diagram_budget_exceeded/);
  await assert.rejects(validateRepository(await fixture(t,valid.replace(' A-->B',' A['+'x'.repeat(32001)+']'))),/diagram_budget_exceeded/);
  await assert.rejects(validateRepository(await fixture(t,valid+'x'.repeat(128*1024))),/file_invalid_or_too_large/);
});
test('rejects a document symlink inside the same repository', async t => {
  const root = await fixture(t, valid, ['docs/diagrams/link.md']);
  await symlink('README.md',path.join(root,'docs/diagrams/link.md'));
  await assert.rejects(validateRepository(root),/symlink_forbidden/);
});

test('rejects an unterminated extra diagram after valid views', async t => {
  const root = await fixture(t, valid + '\n```mermaid\nflowchart LR\n A-->B');
  await assert.rejects(validateRepository(root), /unterminated_mermaid/);
});
test('accepts standard Markdown fence variants like the Python checker', async t => {
  const root=await fixture(t,'  ````Mermaid\nflowchart LR\n A-->B\n  ````\n~~~mermaid\nflowchart LR\n A-->B\n~~~');
  assert.equal((await validateRepository(root)).diagrams,2);
});

test('CLI validates when invoked through a symlink and never silently succeeds', async t => {
  const root = await fixture(t, valid);
  const alias = path.join(root, 'checker.mjs');
  await symlink(fileURLToPath(new URL('./check.mjs', import.meta.url)), alias);
  const result = spawnSync(process.execPath, [alias, '--root', root], {encoding:'utf8'});
  assert.equal(result.status, 0, result.stderr);
  assert.equal(JSON.parse(result.stdout).diagrams, 2);
  await writeFile(path.join(root,'docs/diagrams/README.md'),'No diagrams');
  const invalid = spawnSync(process.execPath, [alias, '--root', root], {encoding:'utf8'});
  assert.equal(invalid.status, 1);
  assert.match(invalid.stderr,/missing_mermaid/);
});
