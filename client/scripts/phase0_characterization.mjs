import { readFileSync, readdirSync, statSync, mkdirSync, writeFileSync } from 'node:fs';
import { join, relative, resolve } from 'node:path';

const clientRoot = resolve(import.meta.dirname, '..');
const repoRoot = resolve(clientRoot, '..');
const srcRoot = join(clientRoot, 'src');
const outputDir = join(repoRoot, 'audit-artifacts');

function walk(dir) {
  const out = [];
  for (const name of readdirSync(dir).sort()) {
    const full = join(dir, name);
    const stat = statSync(full);
    if (stat.isDirectory()) out.push(...walk(full));
    else out.push(full);
  }
  return out;
}

const required = [
  'src/main.tsx',
  'src/pages/LoginPage.tsx',
  'src/pages/ChatsPage.tsx',
  'src/pages/ConnectionsPage.tsx',
  'src/pages/ContactsPage.tsx',
  'src/pages/QueuesPage.tsx',
  'src/pages/ReportsPage.tsx',
  'src/pages/AdminUsersPage.tsx',
  'src/components/domain/chat/ChatView.tsx',
  'src/lib/event-stream.ts',
  'src/stores/auth.ts',
  'src/stores/chats.ts',
];
for (const rel of required) {
  const full = join(clientRoot, rel);
  try {
    statSync(full);
  } catch {
    throw new Error(`missing legacy UI contract file: ${rel}`);
  }
}

const sourceFiles = walk(srcRoot).filter((file) => /\.(ts|tsx|css|json)$/.test(file));
const fileMetrics = sourceFiles.map((file) => {
  const text = readFileSync(file, 'utf8');
  return {
    path: relative(clientRoot, file).replaceAll('\\', '/'),
    lines: text.split(/\r?\n/).length,
    imports: (text.match(/^import\s/gm) || []).length,
    apiReferences: (text.match(/\/api\//g) || []).length,
  };
});

const packageJSON = JSON.parse(readFileSync(join(clientRoot, 'package.json'), 'utf8'));
const report = {
  sourceFiles: fileMetrics.length,
  pages: fileMetrics.filter((f) => f.path.startsWith('src/pages/')).length,
  components: fileMetrics.filter((f) => f.path.startsWith('src/components/')).length,
  services: fileMetrics.filter((f) => f.path.startsWith('src/services/')).length,
  stores: fileMetrics.filter((f) => f.path.startsWith('src/stores/')).length,
  types: fileMetrics.filter((f) => f.path.startsWith('src/types/')).length,
  locales: fileMetrics.filter((f) => f.path.startsWith('src/i18n/locales/')).length,
  scripts: packageJSON.scripts,
  hasAutomatedTestScript: Boolean(packageJSON.scripts?.test),
  hasLintScript: Boolean(packageJSON.scripts?.lint),
  hasTypecheckScript: Boolean(packageJSON.scripts?.typecheck),
  oversizedFiles: fileMetrics.filter((f) => f.lines >= 500).sort((a, b) => b.lines - a.lines),
  files: fileMetrics,
};

mkdirSync(outputDir, { recursive: true });
writeFileSync(join(outputDir, 'wacalls-frontend-characterization.json'), `${JSON.stringify(report, null, 2)}\n`);
console.log(JSON.stringify({
  sourceFiles: report.sourceFiles,
  pages: report.pages,
  oversizedFiles: report.oversizedFiles.length,
  hasAutomatedTestScript: report.hasAutomatedTestScript,
  hasLintScript: report.hasLintScript,
  hasTypecheckScript: report.hasTypecheckScript,
}, null, 2));
