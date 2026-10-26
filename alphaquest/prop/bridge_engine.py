"""Licensed The Bridge CLI execution through the current Windows login.

No license tokens or credentials are read, copied or modified. This invokes only
funded-lab, never collector, live, broker, download or installation commands.
"""
import base64
import json
import os
from pathlib import Path
import subprocess
import time

PRLCTL = '/Applications/Parallels Desktop.app/Contents/MacOS/prlctl'
QUALIFIED_SHA256 = '4b0032d156072fc3aa290c2ac21a644b449e7ccf64335f918a02729250495a61'


def ps_quote(value):
    return "'" + value.replace("'", "''") + "'"


def guest_path(path):
    try:
        relative = Path(path).resolve().relative_to(Path.home().resolve())
    except ValueError as exc:
        raise ValueError('Bridge inputs and output directory must be under your macOS home folder, shared as \\Mac\\Home.') from exc
    return '\\\\Mac\\Home\\' + str(relative).replace('/', '\\')


def powershell(script):
    return [PRLCTL, 'exec', os.environ.get('ALPHAQUEST_BRIDGE_VM', 'Windows 11'), '--current-user',
            'C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe', '-NoProfile', '-NonInteractive',
            '-EncodedCommand', base64.b64encode(script.encode('utf-16-le')).decode()]


def engine_identity():
    if not Path(PRLCTL).is_file():
        raise ValueError('The Bridge runner requires Parallels Desktop and your licensed Windows installation.')
    exe = os.environ.get('ALPHAQUEST_BRIDGE_EXE', 'C:\\Program Files\\The Bridge\\TheBridge-Hosted.exe')
    script = "$ProgressPreference='SilentlyContinue';$ErrorActionPreference='Stop';" + (
        f"$p={ps_quote(exe)};$f=Get-Item -LiteralPath $p;"
        "[PSCustomObject]@{executable=$f.FullName;version=$f.VersionInfo.FileVersion;"
        "sha256=(Get-FileHash -LiteralPath $p -Algorithm SHA256).Hash}|ConvertTo-Json -Compress")
    # Parallels may transiently reject guest RPC while its session starts.
    # Retry only this read-only identity request; never retry an analysis run.
    for attempt in range(2):
        try:
            result = subprocess.run(powershell(script), capture_output=True, text=True, timeout=45)
        except (OSError, subprocess.TimeoutExpired) as exc:
            if attempt == 0:
                continue
            raise ValueError('Cannot reach The Bridge in the running Windows VM.') from exc
        if result.returncode == 0:
            break
        if attempt == 0:
            time.sleep(.5)
    if result.returncode:
        raise ValueError(f'Cannot inspect The Bridge executable (guest RPC exit {result.returncode}). Start the configured Windows VM and check its installation.')
    try:
        identity = json.loads(result.stdout.strip())
    except json.JSONDecodeError as exc:
        raise ValueError('The Bridge identity probe returned no executable metadata.') from exc
    if not identity.get('sha256') or not identity.get('executable'):
        raise ValueError('Incomplete Bridge executable identity.')
    identity['sha256'] = identity['sha256'].lower()
    expected = os.environ.get('ALPHAQUEST_BRIDGE_EXPECTED_SHA256', QUALIFIED_SHA256).lower()
    if identity['sha256'] != expected:
        raise ValueError('The Bridge build differs from the qualified executable. Revalidate the new build before changing ALPHAQUEST_BRIDGE_EXPECTED_SHA256.')
    identity['vm'] = os.environ.get('ALPHAQUEST_BRIDGE_VM', 'Windows 11')
    identity['runner'] = 'Parallels current-user funded-lab CLI; active Bridge license required'
    return identity


def run_bridge(input_file, settings_file, output, identity, progress):
    args = ['funded-lab', '--files', guest_path(input_file), '--settings', guest_path(settings_file), '--out', guest_path(output)]
    # Windows quoting is explicit; shell interpolation never sees user input.
    argv = subprocess.list2cmdline(args)
    script = "$ProgressPreference='SilentlyContinue';$ErrorActionPreference='Stop';" + (
        f"$p=Start-Process -FilePath {ps_quote(identity['executable'])} -ArgumentList {ps_quote(argv)} "
        "-WorkingDirectory 'C:\\OFB' -PassThru;"
        "if(-not $p.WaitForExit(1800000)){$p.Kill();$p.WaitForExit();exit 124};exit $p.ExitCode")
    stdout_path, stderr_path = output.parent / 'runner.stdout.log', output.parent / 'runner.stderr.log'
    progress('Starting licensed The Bridge analysis')
    with stdout_path.open('w') as stdout, stderr_path.open('w') as stderr:
        process = subprocess.Popen(powershell(script), stdout=stdout, stderr=stderr, text=True)
        last = None
        deadline = time.monotonic() + 1860
        while process.poll() is None:
            if time.monotonic() > deadline:
                process.terminate()
                try:process.wait(timeout=5)
                except subprocess.TimeoutExpired:process.kill();process.wait()
                raise ValueError('Lost contact with the Bridge runner. No completed report was published; check the Windows analysis before retrying.')
            log = output / 'run.log'
            if log.is_file():
                with log.open('rb') as stream:
                    stream.seek(max(0, log.stat().st_size - 8192))
                    text = stream.read().decode('utf-8', errors='replace')
                stages = [s.strip('= \r') for s in text.splitlines() if s.startswith('== ')]
                stage = stages[-1] if stages else 'The Bridge is loading and checking the trade export'
                if stage != last:
                    progress(stage)
                    last = stage
            time.sleep(.5)
        if process.returncode:
            detail=stderr_path.read_text(errors='replace').strip()[-500:]
            raise ValueError(f'The Bridge operation failed (runner exit {process.returncode}); no completed report was published. {detail}')
    result_file = output / 'results.json'
    if not result_file.is_file():
        raise ValueError('The Bridge exited without results.json; no completed result was published.')
    if result_file.stat().st_size > 32 * 1024 * 1024:
        raise ValueError('Bridge results exceed the supported metadata limit.')
    result = json.loads(result_file.read_text(encoding='utf-8-sig'))
    if result.get('status') != 'ok' or result.get('exit_code') != 0 or result.get('demo'):
        raise ValueError('The Bridge did not return a successful real-data analysis.')
    if engine_identity()['sha256'] != identity['sha256']:
        raise ValueError('The Bridge executable changed during execution.')
    return result
