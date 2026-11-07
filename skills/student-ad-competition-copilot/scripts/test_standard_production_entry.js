// SIMULATED native provider only; package preparation and guard subprocess are real.
const fs = require('node:fs');
const cp = require('node:child_process');
const path = require('node:path');
const [python, skill, root, casesPath] = process.argv.slice(2);
const source = fs.readFileSync(path.join(skill, 'scripts/standard_production_entry.js'), 'utf8');
const cases = JSON.parse(fs.readFileSync(casesPath, 'utf8'));
(async () => {
  const results = [];
  for (const test of cases) {
    let calls = 0, received, checked, error, outcome;
    const tools = {
      exec_command: async args => {
        const p = cp.spawnSync('powershell.exe', ['-NoProfile', '-NonInteractive', '-Command', args.cmd],
          {encoding:'utf8', maxBuffer:16*1024*1024, env:{...process.env, PYTHONUTF8:'1'}});
        if (p.error) throw p.error;
        if (test.transport === 'malformed') return {exit_code:0, output:'{invalid'};
        if (test.transport === 'missing-status') return {output:p.stdout};
        return {exit_code:p.status, output:p.stdout + p.stderr};
      },
      image_gen__imagegen: async params => {
        calls++; received = params;
        if (test.providerThrows) throw new Error('SIMULATED provider failure');
        return {image_url:'SIMULATED-no-image-created'};
      }
    };
    const config = {python, skill, runDir:root, manifest:test.manifest, payload:test.payload, snapshot:test.snapshot};
    if (test.parameterOverride) config.parameters = {prompt:'SIMULATED forbidden override'};
    try { outcome = await new Function('tools', 'config', source)(tools, config); checked = outcome.checked; }
    catch (e) { error = String(e); }
    const unknown = outcome?.status === 'native-result-unknown';
    if (calls !== test.expectedCalls || Boolean(error || unknown) !== Boolean(test.expectError))
      throw new Error(JSON.stringify({test:test.name,calls,error}));
    if (checked && JSON.stringify(received) !== JSON.stringify(checked.parameters))
      throw new Error('Dispatch did not use checked parameters');
    if (test.providerThrows && (!unknown || !checked?.manifest || !checked?.dispatch_intent))
      throw new Error('Provider failure lost recoverable checked state');
    results.push({name:test.name, calls, blocked:Boolean(error), nativeResultUnknown:unknown, error, checked});
  }
  fs.writeFileSync(path.join(root,'standard-entry-results.json'),JSON.stringify({real_image_calls:0,results},null,2));
  console.log(JSON.stringify({passed:results.length, real_image_calls:0}));
})().catch(e => {console.error(e);process.exitCode=1;});
