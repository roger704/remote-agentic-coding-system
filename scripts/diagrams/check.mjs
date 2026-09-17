import { readFile, realpath, lstat } from 'node:fs/promises';
import path from 'node:path';
import { pathToFileURL } from 'node:url';
import { JSDOM } from 'jsdom';

// Mermaid's parser sanitizes labels through DOMPurify. No document is rendered,
// no scripts are enabled, and no repository content is evaluated as JavaScript.
const dom = new JSDOM('');
globalThis.window = dom.window;
globalThis.document = dom.window.document;
const { default: mermaid } = await import('mermaid');
mermaid.initialize({ startOnLoad: false, securityLevel: 'strict' });

const safeDocument = value => typeof value === 'string'
  && /^docs\/diagrams\/(?:[A-Za-z0-9_-]+\/)*[A-Za-z0-9_.-]+\.md$/.test(value)
  && value.split('/').every(part => !part.startsWith('.'));

async function boundedFile(root, relative) {
  let file = root;
  for (const part of relative.split('/')) {
    file = path.join(file, part);
    if ((await lstat(file)).isSymbolicLink()) throw new Error('symlink_forbidden');
  }
  const resolved = await realpath(file);
  if (!resolved.startsWith(`${root}${path.sep}`)) throw new Error('file_outside_repository');
  const info = await lstat(file);
  if (!info.isFile() || info.size > 128 * 1024) throw new Error('file_invalid_or_too_large');
  return readFile(file, 'utf8');
}

export async function validateRepository(directory) {
  const root = await realpath(directory);
  const manifest = JSON.parse(await boundedFile(root, '.nexus/diagrams.json'));
  if (!manifest || typeof manifest !== 'object' || Array.isArray(manifest)
    || Object.keys(manifest).sort().join(',') !== 'documents,schema_version,source_fingerprint'
    || typeof manifest.source_fingerprint !== 'string' || !/^[a-f0-9]{64}$/.test(manifest.source_fingerprint)
    || manifest.schema_version !== 1 || !Array.isArray(manifest.documents)
    || !manifest.documents.length || manifest.documents.length > 10
    || !manifest.documents.every(safeDocument)
    || new Set(manifest.documents).size !== manifest.documents.length) throw new Error('invalid_diagram_manifest');
  let diagrams = 0;
  for (const document of manifest.documents) {
    const text = await boundedFile(root, document);
    const blocks = [];
    let fence = null;
    let body = [];
    for (const line of text.split(/\r?\n/)) {
      if (fence === null) {
        const opening = line.match(/^ {0,3}(`{3,}|~{3,})mermaid\s*$/i);
        if (opening) { fence = opening[1]; body = []; }
      } else if (new RegExp(`^ {0,3}${fence[0]}{${fence.length},}\\s*$`).test(line)) {
        blocks.push(body.join('\n'));
        fence = null;
      } else body.push(line);
    }
    if (fence !== null) throw new Error(`unterminated_mermaid:${document}`);
    const count = blocks.length;
    if (count < 1) throw new Error(`missing_mermaid:${document}`);
    if (count > 20 || blocks.some(block => [...block].length > 32000)) throw new Error('diagram_budget_exceeded');
    for (const [index, block] of blocks.entries()) {
      if (!/^\s*(?:flowchart|graph|sequenceDiagram|stateDiagram-v2|classDiagram|erDiagram)\b/.test(block)) throw new Error('unsupported_diagram_kind');
      if (block.includes('%%{') || /^\s*click\s|<script|javascript:/im.test(block)) throw new Error('active_directive_forbidden');
      try { await mermaid.parse(block); }
      catch { throw new Error(`invalid_mermaid:${document}:diagram_${index + 1}`); }
    }
    diagrams += count;
  }
  return { ok: true, documents: manifest.documents.length, diagrams };
}

if (process.argv[1] && import.meta.url === pathToFileURL(await realpath(process.argv[1])).href) {
  const args = process.argv.slice(2);
  if (args.length && (args.length !== 2 || args[0] !== '--root')) {
    console.error('Usage: node scripts/diagrams/check.mjs [--root repository]');
    process.exitCode = 1;
  } else {
    try { console.log(JSON.stringify(await validateRepository(args[1] ?? process.cwd()))); }
    catch (error) {
      // Do not print parser messages: they can contain arbitrary document text.
      const code = error instanceof Error && /^(invalid_mermaid:|unterminated_mermaid:|missing_mermaid:|invalid_diagram_manifest$|file_outside_repository$|file_invalid_or_too_large$|symlink_forbidden$|diagram_budget_exceeded$|unsupported_diagram_kind$|active_directive_forbidden$)/.test(error.message) ? error.message : 'diagram_validation_failed';
      console.error(code);
      process.exitCode = 1;
    }
  }
}
