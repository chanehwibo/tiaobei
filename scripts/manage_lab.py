"""Create/status/retire only this project's explicitly owned offline lab.

No host installation, network setup, service change, or permanent deletion.
Retire is a recoverable rename and requires a fresh inventory digest.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
import uuid
import venv

MARKER = ".tiaobei-lab.json"
FOLDERS = ("python", "vm", "iso", "cache", "runs", "sdk-source")
ISO_NAME = "Kylin-Desktop-V11-2603-Release-20260228-X86_64.iso"
ISO_SHA256 = "9d00c0c605e023aa879d895e3aa430d1dfd3eafded6273cf297bc1874f9a29c4"


def checked_root(root, *, require_marker=True):
    raw = Path(root).absolute()
    for path in (raw, *raw.parents):
        if path.is_symlink() or (path.exists() and getattr(path.lstat(), "st_file_attributes", 0) & 0x400):
            raise ValueError("lab path contains a link/reparse point")
    resolved = raw.resolve()
    if resolved.name != "TiaobeiLab" or resolved in (Path.home().resolve(), Path.cwd().resolve(), Path(resolved.anchor)):
        raise ValueError("only a dedicated TiaobeiLab directory is allowed")
    if require_marker:
        marker = json.loads((resolved / MARKER).read_text(encoding="utf-8"))
        if marker.get("owner") != "tiaobei-isolated-lab-v1" or marker.get("root") != str(resolved):
            raise ValueError("lab ownership or location mismatch")
    return resolved


def prepare(root, *, create_python=True):
    root = checked_root(root, require_marker=False)
    if root.exists():
        checked_root(root)
        return inventory(root)
    root.mkdir(parents=False)
    marker = {"owner": "tiaobei-isolated-lab-v1", "root": str(root), "id": str(uuid.uuid4()),
              "host_python": sys.executable, "folders": list(FOLDERS), "network": "disconnected"}
    (root / MARKER).write_text(json.dumps(marker, indent=2), encoding="utf-8")
    for name in FOLDERS:
        (root / name).mkdir()
    if create_python:
        venv.EnvBuilder(with_pip=False, symlinks=False).create(root / "python")
    vmx = '\n'.join((
        '.encoding = "UTF-8"', 'config.version = "8"', 'virtualHW.version = "20"',
        'displayName = "Tiaobei-Galaxy-Kylin-V11-Isolated"', 'guestOS = "otherlinux-64"',
        'memsize = "6144"', 'numvcpus = "4"', 'firmware = "efi"',
        'scsi0.present = "TRUE"', 'scsi0.virtualDev = "lsilogic"',
        'scsi0:0.present = "TRUE"', 'scsi0:0.fileName = "system.vmdk"',
        'ethernet0.present = "FALSE"', 'usb.present = "FALSE"', 'ehci.present = "FALSE"',
        'sound.present = "FALSE"', 'sharedFolder.maxNum = "0"',
        'isolation.tools.hgfs.disable = "TRUE"', 'isolation.tools.copy.disable = "TRUE"',
        'isolation.tools.paste.disable = "TRUE"', 'isolation.tools.dnd.disable = "TRUE"',
        'tools.syncTime = "FALSE"', 'floppy0.present = "FALSE"', '',
    ))
    (root / "vm" / "kylin-v11.vmx").write_text(vmx, encoding="utf-8")
    return inventory(root)


def inventory(root):
    root = checked_root(root)
    unknown = {p.name for p in root.iterdir()} - {*FOLDERS, MARKER}
    if unknown:
        raise ValueError("unmanaged root entries; manual review required")
    rows = []
    for path in sorted(root.rglob("*")):
        info = path.lstat()
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise ValueError("links/reparse points prevent automated retirement")
        if path.name.endswith(".lck"):
            raise ValueError("VM lock present; shut down the lab VM first")
        rows.append([path.relative_to(root).as_posix(), info.st_size, info.st_mtime_ns])
    digest = hashlib.sha256(json.dumps(rows).encode()).hexdigest()
    return {"root": str(root), "inventory_sha256": digest, "entries": rows,
            "retirement": "recoverable rename only; no host software uninstalled"}


def retire(root, confirmation):
    root = checked_root(root)
    state = inventory(root)
    if confirmation != state["inventory_sha256"]:
        raise ValueError("confirmation does not match current inventory")
    marker = json.loads((root / MARKER).read_text(encoding="utf-8"))
    target = root.with_name("TiaobeiLab-retired-" + marker["id"])
    if target.exists() or target.resolve().parent != root.parent:
        raise ValueError("retirement target is not a fresh sibling")
    root.rename(target)
    return {"retired_to": str(target), "recoverable": True}


def attach_iso(root):
    """Attach only the pinned public trial image to the powered-off owned VM."""
    root = checked_root(root)
    inventory(root)
    iso = root / "iso" / ISO_NAME
    digest = hashlib.sha256()
    with iso.open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(block)
    if digest.hexdigest() != ISO_SHA256:
        raise ValueError("official ISO checksum mismatch")
    vmx = root / "vm" / "kylin-v11.vmx"
    original = vmx.read_text(encoding="utf-8")
    if 'ethernet0.present = "FALSE"' not in original or 'scsi0:0.fileName = "system.vmdk"' not in original:
        raise ValueError("VM configuration changed; manual review required")
    if "sata0" in original:
        raise ValueError("CD configuration already exists; refusing overwrite")
    additions = '\n'.join(('sata0.present = "TRUE"', 'sata0:0.present = "TRUE"',
        'sata0:0.deviceType = "cdrom-image"', f'sata0:0.fileName = "{iso.as_posix()}"',
        'sata0:0.startConnected = "TRUE"', 'bios.bootOrder = "cdrom,hdd"', ''))
    vmx.write_text(original + additions, encoding="utf-8")
    return {"iso_sha256": digest.hexdigest(), "attached": True, "vm_started": False}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "status", "retire", "attach-iso"))
    parser.add_argument("--root", type=Path, default=Path.home() / "TiaobeiLab")
    parser.add_argument("--confirm", default="")
    args = parser.parse_args()
    result = (prepare(args.root) if args.action == "prepare" else
              retire(args.root, args.confirm) if args.action == "retire" else
              attach_iso(args.root) if args.action == "attach-iso" else inventory(args.root))
    print(json.dumps(result, ensure_ascii=False, indent=2))
