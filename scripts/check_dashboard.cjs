const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const html = fs.readFileSync(path.join(__dirname, '../src/os_agent_memory/dashboard.html'), 'utf8');
const script = html.match(/<script>([\s\S]*?)<\/script>/)[1];
new vm.Script(script);
const ids = [...html.matchAll(/\bid="([^"]+)"/g)].map(match => match[1]);
if (new Set(ids).size !== ids.length) throw new Error('duplicate DOM ids');
for (const match of script.matchAll(/(?:el|bind)\('([^']+)'/g)) {
  if (!ids.includes(match[1])) throw new Error('missing DOM target: ' + match[1]);
}
console.log('Dashboard JavaScript syntax and DOM targets passed');
