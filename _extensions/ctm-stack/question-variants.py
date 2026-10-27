#!/usr/bin/env python3
"""STACK-owned bootstrap to the canonical native variants adapter."""
import sys
if __name__ == '__main__' and not sys.flags.isolated:
    import os
    os.execv(sys.executable,[sys.executable,'-I',__file__]+sys.argv[1:])
import hashlib,json,os
from pathlib import Path
HERE=Path(__file__).resolve().parent
INSTALL="Install CTM Assessment's native authoring distribution alongside ctm-checkers."

def _folders():
    paths = [HERE.parent / "ctm-checkers"]
    extensions = next((path for path in HERE.parents if path.name == "_extensions"), None)
    if extensions is not None:
        paths += [extensions / "ctm-checkers"] + sorted(extensions.glob("*/ctm-checkers"))
    return list(dict.fromkeys(paths))

def _verify_native(path):
    path = path.resolve()
    manifest = json.loads((path / "native.json").read_text(encoding="utf-8"))
    if manifest.get("version") != 1 or manifest.get("kind") != "native-authoring" or not isinstance(manifest.get("files"), dict):
        raise ValueError("invalid native authoring manifest")
    actual = set()
    for file in path.rglob("*"):
        if file.is_symlink():
            raise ValueError("native authoring source must not contain symlinks")
        if not file.is_file():
            continue
        name = file.relative_to(path).as_posix()
        if name == "native.json" or (file.suffix == ".pyc" and file.parent.name == "__pycache__"):
            continue
        if file.is_symlink() or file.resolve().is_relative_to(path) is False:
            raise ValueError("native authoring source must stay inside its installation")
        actual.add(name)
    if actual != set(manifest["files"]):
        raise ValueError("native authoring file set differs from its manifest")
    for name, expected in manifest["files"].items():
        file = path / name
        if not file.resolve().is_relative_to(path):
            raise ValueError("native authoring path escapes its installation")
        data = file.read_bytes()
        if expected != {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}:
            raise ValueError("native authoring source differs from its manifest: " + name)
    return path

def install_imports():
    """Resolve only explicit/canonical installations before trusted imports."""
    wheel = Path(os.environ["CTM_CHECKERS_WHEEL"]).resolve() if os.environ.get("CTM_CHECKERS_WHEEL") else None
    native = Path(os.environ["CTM_VARIANTS_NATIVE"]).resolve() if os.environ.get("CTM_VARIANTS_NATIVE") else None
    for folder in _folders():
        if not folder.is_dir():
            continue
        if wheel is None and (folder / "checkers.json").is_file():
            descriptor = json.loads((folder / "checkers.json").read_text(encoding="utf-8"))
            candidate = (folder / descriptor["wheel"]).resolve()
            if not candidate.is_relative_to(folder.resolve()):
                raise ValueError("checker wheel path escapes its installation")
            if candidate.is_file():
                wheel = candidate
        if native is None and (folder / "native-authoring" / "native.json").is_file():
            native = folder / "native-authoring"
    if wheel is None or not wheel.is_file() or native is None:
        raise ValueError(INSTALL)
    descriptor = json.loads((wheel.parent / "checkers.json").read_text(encoding="utf-8"))
    if ((wheel.parent / descriptor["wheel"]).resolve() != wheel
            or descriptor.get("sha256") != hashlib.sha256(wheel.read_bytes()).hexdigest()):
        raise ValueError("checker wheel differs from its canonical descriptor")
    native = _verify_native(native)
    part=descriptor['parts']['stack']
    stack=(wheel.parent/part['wheel']).resolve()
    if not stack.is_relative_to(wheel.parent) or hashlib.sha256(stack.read_bytes()).hexdigest()!=part['sha256']:
        raise ValueError('STACK wheel differs from its canonical descriptor')
    sys.path[:0] = [str(wheel),str(stack),str(native),str(HERE)]

def supervised(raw, *, timeout=300, worker_args=()):
    """Bound the whole request, including stalled input, bootstrap and teardown.

    raw=None passes the real stdin descriptor to the isolated worker, so reading
    a caller that never closes its pipe is covered by the same outer deadline.
    Byte requests remain available to component callers and focused contracts.
    """
    import signal
    import subprocess
    import tempfile
    import threading
    import time
    output_limit = 16 * 1024 * 1024
    deadline = time.monotonic() + timeout
    reason = []

    def kill(child):
        if os.name != "nt":
            try:
                os.killpg(child.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass  # Child exited between the deadline and group cleanup.
        else:
            try:
                subprocess.run(["taskkill", "/F", "/T", "/PID", str(child.pid)], timeout=2,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
            except (OSError, subprocess.TimeoutExpired):
                pass
            finally:
                try:
                    child.kill()
                except ProcessLookupError:
                    pass

    # Files avoid unbounded communicate() buffers. The watcher aborts a worker
    # crossing the aggregate output budget; the returned buffers are capped.
    with tempfile.TemporaryFile() as output, tempfile.TemporaryFile() as errors:
        child = subprocess.Popen([sys.executable, "-I", str(Path(__file__).resolve()), "--stdin", "--worker", *worker_args],
            stdin=sys.stdin.buffer if raw is None else subprocess.PIPE,
            stdout=output, stderr=errors, start_new_session=os.name != "nt")
        def watch():
            while True:
                if os.fstat(output.fileno()).st_size + os.fstat(errors.fileno()).st_size > output_limit:
                    reason.append("total native request output budget exceeded")
                    kill(child)
                    return
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    reason.append("total native request time budget exceeded")
                    kill(child)
                    return
                try:
                    child.wait(timeout=min(0.05, remaining))
                    if os.fstat(output.fileno()).st_size + os.fstat(errors.fileno()).st_size > output_limit:
                        reason.append("total native request output budget exceeded")
                    return
                except subprocess.TimeoutExpired:
                    pass
        watcher = threading.Thread(target=watch, name="ctm-native-request-budget", daemon=True)
        watcher.start()
        try:
            child.communicate(raw)
        finally:
            if child.stdin is not None:
                child.stdin.close()
            watcher.join()
            if os.name != "nt":
                kill(child)  # Also retire author-created descendants on success.
        output.seek(0)
        errors.seek(0)
        stdout = output.read(output_limit)
        stderr = errors.read(max(0, output_limit - len(stdout)))
        if reason:
            return 1, b"", stderr + ("ctm-stack variants: " + reason[0] + "\n").encode()
        return child.returncode, stdout, stderr

def parse_source(source):
    from ctm_variants.stack_component import parse_source as parse
    return parse(source)

def current_source(payload):
    from ctm_variants.stack_component import current_source as fresh
    return fresh(payload)

def request(payload):
    from ctm_variants.stack_component import request as resolve
    options,_ = parse_source(payload.get('source',''))
    if options.get('cas',payload.get('backend','sympy')) == 'maxima':
        from ctm_stack_native import NativeBackend
        folder = next((p for p in _folders() if (p/'checkers.json').is_file()), None)
        if os.environ.get('CTM_CHECKERS_WHEEL'):
            folder = Path(os.environ['CTM_CHECKERS_WHEEL']).resolve().parent
        return resolve(payload,backend=NativeBackend(checker_folder=folder))
    return resolve(payload)

def configured_backend(payload):
    """Resolve file-command defaults with the same ctm-libs settings reader.

    Quarto supplies merged metadata; the canonical reader restores individual
    settings hidden by a nearer section map. Do not infer the engine from a
    downloaded decision or a retained replay tape.
    """
    import subprocess
    cli=os.environ.get('CTM_VARIANTS_QUARTO','quarto')
    root=Path(payload['projectRoot']).resolve()
    source=(root/payload['file']).resolve()
    inspection=json.loads(subprocess.check_output([cli,'inspect',str(source)],cwd=root,timeout=30))
    formats=inspection.get('formats',{})
    html=next((value for key,value in formats.items() if key=='html' or value.get('identifier',{}).get('base-format')=='html'),{})
    metadata=html.get('metadata',{})
    project=inspection.get('project',{})
    configuration=project.get('config',{})
    defaults=configuration.get('profile',{})
    profiles=os.environ.get('QUARTO_PROFILE')
    profiles=profiles.split(',') if profiles else defaults.get('default',[]) if isinstance(defaults,dict) else []
    if isinstance(profiles,str):profiles=[profiles]
    # Installed flat and owner-prefixed layouts both use ctm-libs' own reader.
    candidates=[HERE.parent/'ctm-libs']
    for parent in [root,*source.parents]:
        ext=parent/'_extensions'
        candidates += [ext/'ctm-libs',*sorted(ext.glob('*/ctm-libs'))]
        if parent==root:break
    library=next((folder for folder in candidates if (folder/'read-settings.ts').is_file()),None)
    if library is None:raise ValueError('Install ctm-libs to resolve the authored STACK backend')
    settings=json.loads(subprocess.check_output([cli,'run',str(library/'read-settings.ts')],cwd=root,
        input=json.dumps({'projectDirectory':project.get('dir',str(root)),'inputFile':str(source),
            'profiles':profiles,'sections':['stack'],'documentMeta':{'stack':metadata.get('stack',{})}}).encode(),timeout=30))
    if settings.get('errors'):raise ValueError('; '.join(settings['errors']))
    backend=settings.get('settings',{}).get('stack',{}).get('cas',{}).get('value','sympy')
    if backend not in ('sympy','maxima'):raise ValueError('stack.cas must be sympy or maxima')
    return backend

def file_request(payload, command):
    """Build the same version-1 request from current source and explicit files.

    Downloaded review records, source text and project selectors are never
    authoritative. Only the original lease and explicit decisions are carried
    into a fresh component request.
    """
    import re
    from ctm_variants import history
    from ctm_variants.review import _path
    project = str(Path(payload["projectRoot"]).resolve())
    label = payload["label"]
    manifest = payload.get("manifest")
    if manifest is None:
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", label) or ".." in label:
            raise ValueError("this label needs an explicit --manifest path inside the project")
        manifest = "_variants/" + label + ".yml"
    path = _path(project, manifest)
    manifest = path.relative_to(Path(project)).as_posix()
    file = _path(project, payload["file"]).relative_to(Path(project)).as_posix()
    request_payload = current_source({"projectRoot": project, "file": file,
        "sourceFile": file, "label": label, "manifest": manifest, "version": 1,
        "approval": "required", "renderMode": "review"})
    if 'cas' not in request_payload['options']:
        request_payload['backend']=configured_backend(request_payload)
    value, lease = history.load(path, label)
    if command == "generate25more":
        expected = payload.get("expectedBaseHash", lease)
        if expected != lease:
            raise ValueError("manifest changed; rebuild review before generating more proposals")
        return dict(request_payload, action="generate", baseHash=expected)
    if command == "resolve":
        return dict(request_payload, action="resolve")
    if command == "review":
        if lease is None or not value["proposals"]:
            raise ValueError("no retained proposals; run generate25more before reviewing decisions")
        return dict(request_payload, action="resolve")
    if command != "apply":
        raise ValueError("unknown file authoring command")
    downloaded_path = Path(payload["requestFile"])
    if not downloaded_path.is_file() or downloaded_path.stat().st_size > 1024 * 1024:
        raise ValueError("downloaded decision request must be a file of at most 1 MiB")
    downloaded = json.loads(downloaded_path.read_text(encoding="utf-8"))
    if (type(downloaded) is not dict or type(downloaded.get("version")) is not int
            or downloaded["version"] != 1 or downloaded.get("label") != label
            or downloaded.get("action") not in ("decide", "decide-many")
            or "baseHash" not in downloaded):
        raise ValueError("downloaded request needs this label, version 1, explicit decisions and its original baseHash")
    if not isinstance(downloaded.get("manifest"), str) or _path(project, downloaded["manifest"]) != path:
        raise ValueError("downloaded manifest differs from the selected --manifest")
    action = downloaded["action"]
    key = "decision" if action == "decide" else "decisions"
    return dict(request_payload, action=action, baseHash=downloaded["baseHash"],
                **{key: downloaded.get(key)})

def review_html(result, payload, connected_endpoint=None):
    """Use the shared review UI, prefilled for this explicit local operation."""
    from ctm_variants.review import document
    page = document(result, connected_endpoint=connected_endpoint)
    # The existing disconnected UI accepts project/manifest text controls. Keep
    # its exported decision protocol unchanged; --file supplies source context
    # when a downloaded request is applied through this component wrapper.
    defaults = json.dumps({"root": payload["projectRoot"], "path": payload["manifest"]},
                          ensure_ascii=True).replace("<", "\\u003c")
    script = "<script>Object.entries(" + defaults + ").forEach(([id,value])=>{document.getElementById(id).value=value;});</script>"
    return page.rsplit("</html>", 1)[0] + script + "</html>"

def main(argv=None):
    import argparse
    import contextlib
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", nargs="?", choices=("generate25more", "review", "resolve", "apply"))
    parser.add_argument("request_file", nargs="?", type=Path, help="downloaded decision JSON for apply")
    parser.add_argument("--stdin", action="store_true", help="read the version-1 JSON request")
    parser.add_argument("--errors-to-stdout", action="store_true", help="include the bounded build diagnostic in pandoc.pipe failures")
    parser.add_argument("--project", type=Path, help="course project root for file authoring")
    parser.add_argument("--file", help="authored source file inside the project")
    parser.add_argument("--label", help="unique authored exercise label")
    parser.add_argument("--manifest", help="manifest inside the project (default: _variants/LABEL.yml)")
    parser.add_argument("--base-hash", help="expected manifest lease for generate25more (64 hex characters, or null)")
    parser.add_argument("--html", type=Path, help="write a disconnected review HTML file")
    parser.add_argument("--connected-endpoint", help=argparse.SUPPRESS)
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--file-command", choices=("generate25more", "review", "resolve", "apply"), help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.stdin:
        if args.command or args.request_file or any(value is not None for value in (args.project, args.file, args.label, args.manifest)):
            parser.error("choose --stdin or a file authoring command")
    elif (args.command is None or args.project is None or not args.file or not args.label
          or args.worker or args.file_command):
        parser.error("file authoring needs --project, --file, --label and generate25more, review, resolve or apply")
    if args.command == "apply" and args.request_file is None:
        parser.error("apply needs a downloaded decision JSON file")
    if args.command not in (None, "apply") and args.request_file is not None:
        parser.error("only apply accepts a downloaded decision JSON file")
    if args.base_hash is not None:
        import re
        if args.command != "generate25more" or (args.base_hash != "null" and not re.fullmatch(r"[0-9a-f]{64}", args.base_hash)):
            parser.error("--base-hash requires generate25more and a 64-character hex lease or null")
    try:
        if args.stdin and args.worker:
            raw = sys.stdin.buffer.read(1024 * 1024 + 1)
        elif args.stdin:
            raw = None  # The supervised worker owns the potentially stalled read.
        else:
            payload = {"projectRoot": str(args.project.resolve()), "file": args.file,
                       "label": args.label, "manifest": args.manifest}
            if args.base_hash is not None:
                payload["expectedBaseHash"] = None if args.base_hash == "null" else args.base_hash
            if args.request_file is not None:
                payload["requestFile"] = str(args.request_file.resolve())
            raw = json.dumps(payload, ensure_ascii=True, allow_nan=False).encode()
        if raw is not None and len(raw) > 1024 * 1024:
            raise ValueError("component variants request exceeds byte limit")
        if not args.worker:
            worker_args = ["--file-command", args.command] if args.command else []
            if args.html is not None:
                worker_args += ["--html", str(args.html.resolve())]
            if args.connected_endpoint is not None:
                worker_args += ["--connected-endpoint", args.connected_endpoint]
            code, stdout, stderr = supervised(raw, worker_args=worker_args)
            sys.stdout.buffer.write(stdout)
            sys.stderr.buffer.write(stderr)
            if code and args.errors_to_stdout:
                diagnostic=next((line for line in reversed(stderr.splitlines()) if line.startswith(b'ctm-stack variants: ')),None)
                if diagnostic:
                    sys.stdout.buffer.write(diagnostic.decode('utf-8',errors='replace')[:4096].encode('utf-8')+b'\n')
            return code
        install_imports()
        with contextlib.redirect_stdout(sys.stderr):
            payload = json.loads(raw)
            request_file = payload.get("requestFile") if args.file_command else None
            if args.file_command:
                payload = file_request(payload, args.file_command)
            if args.html is not None:
                from ctm_variants.review import _path
                protected = {_path(payload["projectRoot"], payload["manifest"]),
                             _path(payload["projectRoot"], payload.get("sourceFile", payload["file"]))}
                if request_file:
                    protected.add(Path(request_file).resolve())
                if args.html.resolve() in protected:
                    raise ValueError("review HTML must not replace source, manifest or downloaded decisions")
                args.html.parent.mkdir(parents=True, exist_ok=True)
                if args.html.exists() and not args.html.is_file():
                    raise ValueError("review HTML output must be a file")
            result = request(payload)
            if args.html is not None:
                try:
                    args.html.write_text(review_html(result, payload, args.connected_endpoint), encoding="utf-8")
                except OSError as error:
                    raise ValueError("variant operation completed but review HTML could not be written; run review --html again: " + str(error)) from error
        print(json.dumps(result, ensure_ascii=True, allow_nan=False))
        return 0
    except Exception as error:
        print("ctm-stack variants: " + str(error), file=sys.stderr)
        return 1

if __name__ == '__main__':
    sys.exit(main())
