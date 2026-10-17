"""Pristine GCL STACK images; each observation still starts a new OS process.

Images are local build artifacts, never an observation cache. The manifest is
checked against the actual runtime, pinned checkout and builder on every use.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import platform
import re
import subprocess

GCL_DEFAULTS = {"GCL_GC_PAGE_THRESH": "0.2", "GCL_GC_ALLOC_MIN": "0.01",
                "GCL_GC_PAGE_MAX": "0.05", "GCL_MEM_MULTIPLE": "0.2"}


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def environment(home):
    env = os.environ.copy()
    for key, value in GCL_DEFAULTS.items():
        env.setdefault(key, value)
    for key, suffix in (("MAXIMA_USERDIR", ""), ("MAXIMA_TEMPDIR", "tmp"), ("MAXIMA_OBJDIR", "obj")):
        env[key] = str(Path(home) / suffix)
    return env


def runtime_identity(executable):
    from .maxima_runner import _command, NativeProcessError
    output = _command([executable, "--very-quiet",
                       '--batch-string=display2d:false$linel:10000$print(sconcat("NATIVE-IMAGE-BUILD|",build_info()))$'
                       'print(sconcat("NATIVE-IMAGE-LISP|",build_info()@lisp_name))$'
                       'print(sconcat("NATIVE-IMAGE-LISP-VERSION|",build_info()@lisp_version))$quit()$'], 30)
    values = {}
    for key in ('BUILD', 'LISP', 'LISP-VERSION'):
        marker = 'NATIVE-IMAGE-'+key+'|'
        records = [line.removeprefix(marker).strip() for line in output.splitlines() if line.startswith(marker)]
        if len(records) != 1 or not records[0]:
            raise NativeProcessError(f"Missing or duplicate actual Maxima {key} record; output={output[-3000:]!r}")
        values[key] = records[0]
    if values['LISP'] not in {'GCL', 'GNU Common Lisp (GCL)'}:
        raise NativeProcessError(f"Preloaded images require the installed GCL Maxima backend; runtime={values!r}")
    return values


def identity(source, executable):
    from .maxima_runner import STACK_SHA, NativeProcessError, _command
    overrides = sorted(key for key in os.environ if
                       key.startswith('MAXIMA_') or key in {'VERPKGLIBDIR', 'LISP', 'LISP_OPTIONS'} or
                       (key.startswith('GCL_') and key not in GCL_DEFAULTS))
    if overrides:
        raise NativeProcessError('Unsupported native-image runtime override variables: '+', '.join(overrides))
    source = Path(source).resolve()
    if _command(["git", "-C", str(source), "rev-parse", "HEAD"], 10).strip() != STACK_SHA:
        raise NativeProcessError("Image requires the pinned STACK checkout")
    # Reject modified sources: a matching HEAD alone is insufficient provenance.
    if _command(["git", "-C", str(source), "status", "--porcelain", "--untracked-files=no"], 10).strip():
        raise NativeProcessError("Image requires a clean STACK checkout")
    runtime = _command([executable, "--list-avail"], 15).strip()
    build_info = runtime_identity(executable)
    packages = _command(["dpkg-query", "-W", "-f=${Package}=${Version}\\n", "maxima", "maxima-share", "libc6"], 15)
    binaries = sorted(Path("/usr/lib/maxima").glob("*/binary-gcl/maxima"))
    if len(binaries) != 1:
        raise NativeProcessError("Expected exactly one installed Maxima GCL binary")
    linked = _command(["ldd", str(binaries[0])], 15)
    libraries = sorted({str(Path(path).resolve()) for path in re.findall(r'(/[^\s()]+)', linked)})
    if not libraries:
        raise NativeProcessError("Cannot fingerprint the GCL shared libraries")
    return {"schema_version": 1, "stack_sha": STACK_SHA, "source": str(source),
            "maxima": str(Path(executable).resolve()), "maxima_sha256": digest(Path(executable).resolve()),
            "version": _command([executable, "--version"], 15).strip(),
            "runtime": runtime, "build_info": build_info, "lisp_binary_sha256": digest(binaries[0]),
            "shared_libraries_sha256": {path: digest(path) for path in libraries},
            "packages": packages, "platform": platform.platform(),
            "runner_image": {key: os.environ.get(key) for key in ('ImageOS', 'ImageVersion')},
            "machine": platform.machine(), "builder_sha256": digest(__file__),
            "runner_sha256": digest(Path(__file__).with_name("maxima_runner.py")),
            "gcl_environment": {k: os.environ.get(k, v) for k, v in GCL_DEFAULTS.items()}}


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def validate(directory, source, executable):
    from .maxima_runner import NativeProcessError
    directory = Path(directory).resolve()
    manifest = json.loads((directory / "manifest.json").read_text())
    expected = identity(source, executable)
    if manifest.get("identity") != expected or manifest.get("key") != fingerprint(expected):
        raise NativeProcessError("Preloaded image provenance differs from this runtime/source/builder")
    image = directory / "stack-gcl"
    if not image.is_file() or manifest.get("image_sha256") != digest(image):
        raise NativeProcessError("Preloaded image is missing or its digest differs")
    status = directory / 'cache-status.json'
    if status.exists():
        cache_status = json.loads(status.read_text()).get('status')
        if cache_status not in {'hit', 'built'}:
            raise NativeProcessError('Invalid native image cache status')
        manifest = {**manifest, 'cache_status': cache_status}
    return manifest


def command(directory, batch):
    return [str(Path(directory).resolve() / "stack-gcl"), "-eval", "(cl-user::run)",
            "-f", "--", "--very-quiet", f"--batch={batch}"]


def build(directory, source, executable):
    from .maxima_runner import make_batch, NativeProcessError
    directory = Path(directory).resolve()
    expected = identity(source, executable)
    directory.mkdir(parents=True, exist_ok=True)
    home = directory / "build-home"
    if home.exists():
        import shutil
        shutil.rmtree(home)
    home.mkdir()
    (home / "obj").mkdir()
    # No warm-up/probe/fixture AT calls are allowed before saving this baseline.
    batch = make_batch(Path(source).resolve(), [], home, 0).split('print("STACKNATIVE-BEGIN|')[0]
    batch = (':lisp (ensure-directories-exist (concatenate \'string maxima::*maxima-objdir* "/"))\n'
             + batch)
    image = directory / "stack-gcl"
    image.unlink(missing_ok=True)
    batch += f'\n:lisp (si::save-system {json.dumps(str(image))})\n'
    build_file = directory / "build.mac"
    build_file.write_text(batch, encoding="utf-8")
    result = subprocess.run([executable, "--very-quiet", f"--batch={build_file}"],
                            env=environment(home), capture_output=True, text=True, timeout=300)
    (directory / "build.log").write_text(result.stdout + result.stderr, encoding="utf-8")
    if result.returncode or not image.is_file():
        raise NativeProcessError(f"GCL image build failed: {(result.stdout + result.stderr)[-3000:]}")
    image.chmod(0o555)
    manifest = {"identity": expected, "key": fingerprint(expected), "image_sha256": digest(image)}
    (directory / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return validate(directory, source, executable)
