#!/usr/bin/env python3
import os
import site
import re

def patch_spec(spec_path="Deluge.spec"):
    site_pkgs = site.getsitepackages()[0]

    # Standard library modules to explicitly mandate
    REQUIRED_STDLIB = [
        "subprocess",
        "threading",
        "asyncio",
        "logging",
        "multiprocessing",
        "xml",
        "concurrent",
        "gettext",
        "argparse",
        "contextvars",
        "_contextvars",
    ]

    ignored_dirs = {
        "__pycache__",
        "test",
        "tests",
        "idlelib",
        "tkinter",
        "turtledemo",
        "pip",
        "wheel",
    }
    ignored_exts = (".a", ".o", ".pyc")

    extra_datas = []

    # Walk site-packages strictly for non-python data assets
    if os.path.exists(site_pkgs):
        for root, dirs, files in os.walk(site_pkgs):
            dirs[:] = [
                d
                for d in dirs
                if d not in ignored_dirs
                and not d.endswith(".dist-info")
                and not d.endswith(".egg-info")
            ]
            for f in files:
                if f.endswith(ignored_exts) or f.endswith(".py"):
                    continue
                full_p = os.path.join(root, f)
                rel_p = os.path.relpath(full_p, site_pkgs)
                dest_dir = os.path.dirname(rel_p)
                extra_datas.append((full_p, dest_dir if dest_dir else "."))

    with open(spec_path, "r") as f:
        content = f.read()

    # 1. Inject extra_datas variable definition at top of spec
    injection = f"extra_datas = {extra_datas}\n"
    content = content.replace("a = Analysis(", injection + "a = Analysis(")
    content = content.replace("datas=datas,", "datas=datas + extra_datas,")

    # 2. Append required stdlib imports to hiddenimports=[...] safely
    hidden_imports_str = ", ".join([f"'{mod}'" for mod in REQUIRED_STDLIB])

    if "hiddenimports=[" in content:
        content = content.replace("hiddenimports=[", f"hiddenimports=[{hidden_imports_str}, ")
    else:
        # If hiddenimports isn't explicitly defined in Analysis, add it as a keyword argument
        content = content.replace("datas=datas", f"hiddenimports=[{hidden_imports_str}],\n    datas=datas")

    with open(spec_path, "w") as f:
        f.write(content)

if __name__ == "__main__":
    patch_spec()
