#!/usr/bin/env python3
import os
import site
import sysconfig

def patch_spec(spec_path="Deluge.spec"):
    site_pkgs = site.getsitepackages()[0]
    stdlib_path = sysconfig.get_path("stdlib")

    # Essential standard library packages that must be bundled
    REQUIRED_STDLIB_MODULES = [
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

    extra_imports = [f"'{mod}'" for mod in REQUIRED_STDLIB_MODULES]
    hidden_str = f"hiddenimports=[{', '.join(extra_imports)}],"

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

    # Collect non-python assets from site-packages
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

    # Inject forced hidden imports and site-packages datas
    injection = f"extra_datas = {extra_datas}\n"
    content = content.replace("a = Analysis(", injection + "a = Analysis(")
    content = content.replace("datas=datas,", "datas=datas + extra_datas,")

    # Force hiddenimports in Analysis
    if "hiddenimports=[" in content:
        content = content.replace("hiddenimports=[", f"hiddenimports=[{', '.join(extra_imports)}, ")
    else:
        content = content.replace("a = Analysis(", f"a = Analysis(\n    {hidden_str}")

    with open(spec_path, "w") as f:
        f.write(content)

if __name__ == "__main__":
    patch_spec()
