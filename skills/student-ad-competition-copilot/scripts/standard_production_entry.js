// Function body: new Function('tools', 'config', source)(tools, config).
// Keep preparation, actual package guard and native invocation in this one call.
return (async () => {
  const keys = ['python', 'skill', 'runDir', 'manifest', 'payload', 'snapshot'];
  if (Object.keys(config).sort().join() !== keys.sort().join() ||
      !keys.every(k => typeof config[k] === 'string' && config[k].trim()))
    throw new Error('Only standard entry paths are accepted; no prompt or parameter overrides');
  if (typeof tools.image_gen__imagegen !== 'function')
    throw new Error('Native image tool unavailable; no dispatch');
  const quote = x => "'" + x.replace(/'/g, "''") + "'";
  const argv = [config.python, '-X', 'utf8', '-B', config.skill + '/scripts/standard_production_entry.py',
    '--run-dir', config.runDir, '--manifest', config.manifest, '--payload', config.payload, '--snapshot', config.snapshot];
  let result = await tools.exec_command({cmd: '& ' + argv.map(quote).join(' '), shell: 'powershell',
    login: false, max_output_tokens: 16000});
  let output = result.output || '';
  while (result.session_id && result.exit_code === undefined) {
    result = await tools.write_stdin({session_id: result.session_id, chars: '', yield_time_ms: 1000, max_output_tokens: 16000});
    output += result.output || '';
  }
  if (result.exit_code !== 0) throw new Error('Standard production blocked: ' + output);
  const checked = JSON.parse(output.trim());
  if (checked.status !== 'ready-for-native-dispatch' || checked.tool !== 'image_gen.imagegen' ||
      !checked.receipt?.sha256 || !checked.manifest?.sha256 || !checked.dispatch_intent?.sha256 || checked.content_pass_granted !== false)
    throw new Error('Missing checked dispatch evidence');
  // No caller-supplied callback or alternative parameters in the production entry.
  try {
    const generated = await tools.image_gen__imagegen(checked.parameters);
    return {status:'native-returned', checked, generated};
  } catch (error) {
    // A transport/provider error is not evidence of non-execution. Keep the
    // checked manifest visible; the persistent intent prevents a branch retry.
    return {status:'native-result-unknown', checked, error:String(error),
      recovery:'Reconcile actual native events using checked.manifest; no automatic retry or completed release.'};
  }
})();
