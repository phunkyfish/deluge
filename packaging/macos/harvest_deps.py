#!/usr/bin/env python3
import glob
import os
import shutil
import subprocess
import sys

EXCLUDED_NAMES = {"libnode", "libruby"}

def copy_with_symlinks(src, dest_dir):
    filename = os.path.basename(src)
    dest_path = os.path.join(dest_dir, filename)

    if os.path.exists(dest_path) or os.path.islink(dest_path):
        return

    if os.path.islink(src):
        link_target = os.readlink(src)
        os.symlink(link_target, dest_path)
        real_src = os.path.realpath(src)
        if os.path.exists(real_src):
            copy_with_symlinks(real_src, dest_dir)
    else:
        shutil.copy2(src, dest_path)
        os.chmod(dest_path, 0o755)

def get_deps(file_path, brew_prefix):
    try:
        out = subprocess.check_output(["otool", "-L", file_path], text=True)
        deps = []
        for line in out.splitlines()[1:]:
            dep = line.strip().split()[0]
            base_name = os.path.basename(dep)
            if any(base_name.startswith(ex) for ex in EXCLUDED_NAMES):
                continue

            real_dep = os.path.realpath(dep)
            if (
                real_dep.startswith(brew_prefix)
                or dep.startswith("/opt/homebrew")
                or dep.startswith("/usr/local")
                or "Cellar" in dep
            ):
                deps.append((dep, real_dep))
        return deps
    except Exception:
        return []

def main():
    if len(sys.argv) < 3:
        print("Usage: harvest_deps.py <app_frameworks_dir> <brew_prefix>")
        sys.exit(1)

    fw_dir = os.path.abspath(sys.argv[1])
    brew_prefix = os.path.realpath(sys.argv[2])

    processed = set()
    while True:
        current_files = set()
        for root, _, files in os.walk(fw_dir):
            for file in files:
                if file.endswith(".dylib") or file.endswith(".so"):
                    current_files.add(os.path.join(root, file))

        new_files = current_files - processed
        if not new_files:
            break
        for f in new_files:
            processed.add(f)
            if os.path.islink(f):
                continue
            for raw_path, real_path in get_deps(f, brew_prefix):
                src_to_copy = (
                    raw_path
                    if (os.path.exists(raw_path) or os.path.islink(raw_path))
                    else real_path
                )
                if os.path.exists(src_to_copy) or os.path.islink(src_to_copy):
                    copy_with_symlinks(src_to_copy, fw_dir)

    all_binaries = [
        b
        for b in glob.glob(os.path.join(fw_dir, "*.dylib"))
        + glob.glob(os.path.join(fw_dir, "*.so"))
        if not os.path.islink(b)
    ]
    for binary in all_binaries:
        name = os.path.basename(binary)
        subprocess.run(
            ["install_name_tool", "-id", f"@rpath/{name}", binary],
            stderr=subprocess.DEVNULL,
        )
        try:
            out = subprocess.check_output(["otool", "-L", binary], text=True)
            for line in out.splitlines()[1:]:
                dep = line.strip().split()[0]
                if not dep.startswith("/System") and not dep.startswith("/usr/lib"):
                    dep_name = os.path.basename(dep)
                    subprocess.run(
                        [
                            "install_name_tool",
                            "-change",
                            dep,
                            f"@loader_path/{dep_name}",
                            binary,
                        ],
                        stderr=subprocess.DEVNULL,
                    )
        except Exception:
            pass

if __name__ == "__main__":
    main()
