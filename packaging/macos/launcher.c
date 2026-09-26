#include <Python.h>
#include <libgen.h>
#include <limits.h>
#include <mach-o/dyld.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

int install_cli_symlinks(const char *exec_dir) {
    char bundle[PATH_MAX];
    snprintf(bundle, sizeof(bundle), "%s/..", exec_dir);

    char real_bundle[PATH_MAX];
    if (!realpath(bundle, real_bundle)) return 1;

    char cmd[4096];
    snprintf(cmd, sizeof(cmd),
        "osascript -e 'do shell script \""
        "mkdir -p /usr/local/bin && "
        "ln -sf \\\"%s/MacOS/Deluge\\\" /usr/local/bin/deluge && "
        "ln -sf \\\"%s/MacOS/deluged\\\" /usr/local/bin/deluged && "
        "ln -sf \\\"%s/MacOS/deluge-web\\\" /usr/local/bin/deluge-web && "
        "ln -sf \\\"%s/MacOS/deluge-console\\\" /usr/local/bin/deluge-console"
        "\" with administrator privileges'",
        real_bundle, real_bundle, real_bundle, real_bundle
    );

    int status = system(cmd);
    if (status == 0) {
        printf("Successfully installed CLI symlinks in /usr/local/bin\n");
    } else {
        fprintf(stderr, "Failed or cancelled installing CLI symlinks.\n");
    }
    return status;
}

int main(int argc, char *argv[]) {
    char path[PATH_MAX];
    uint32_t size = sizeof(path);
    if (_NSGetExecutablePath(path, &size) != 0) return 1;

    char resolved_path[PATH_MAX];
    if (!realpath(path, resolved_path)) return 1;
    char *exec_dir = dirname(resolved_path);

    // Check if invoked purely to install CLI symlinks
    if (argc > 1 && strcmp(argv[1], "--install-cli") == 0) {
        return install_cli_symlinks(exec_dir);
    }

    char zip_path[PATH_MAX], fw_dir[PATH_MAX], res_dir[PATH_MAX], schema_dir[PATH_MAX], typelib_dir[PATH_MAX];
    snprintf(zip_path, sizeof(zip_path), "%s/../Resources/base_library.zip", exec_dir);
    snprintf(fw_dir, sizeof(fw_dir), "%s/../Frameworks", exec_dir);
    snprintf(res_dir, sizeof(res_dir), "%s/../Resources", exec_dir);
    snprintf(schema_dir, sizeof(schema_dir), "%s/../Resources/share/glib-2.0/schemas", exec_dir);
    snprintf(typelib_dir, sizeof(typelib_dir), "%s/../Resources/girepository-1.0", exec_dir);

    char real_fw[PATH_MAX], real_res[PATH_MAX];
    if (!realpath(fw_dir, real_fw)) return 1;
    if (!realpath(res_dir, real_res)) return 1;

    char cache_path[PATH_MAX];
    snprintf(cache_path, sizeof(cache_path), "%s/lib/gdk-pixbuf-2.0/2.10.0/loaders.cache", real_res);

    unsetenv("DYLD_FALLBACK_LIBRARY_PATH");
    unsetenv("DYLD_FALLBACK_FRAMEWORK_PATH");
    unsetenv("DYLD_LIBRARY_PATH");
    unsetenv("DYLD_FRAMEWORK_PATH");

    setenv("DYLD_LIBRARY_PATH", real_fw, 1);
    setenv("DYLD_FRAMEWORK_PATH", real_fw, 1);
    setenv("GDK_PIXBUF_MODULEDIR", real_fw, 1);
    setenv("GDK_PIXBUF_MODULE_FILE", cache_path, 1);
    setenv("GI_TYPELIB_PATH", typelib_dir, 1);
    setenv("GSETTINGS_SCHEMA_DIR", schema_dir, 1);

    char xdg_dirs[PATH_MAX * 2];
    snprintf(xdg_dirs, sizeof(xdg_dirs), "%s:%s/share", real_res, real_res);
    setenv("XDG_DATA_DIRS", xdg_dirs, 1);

    char icon_dirs[PATH_MAX];
    snprintf(icon_dirs, sizeof(icon_dirs), "%s/share/icons", real_res);
    setenv("XDG_DATA_HOME", icon_dirs, 1);

    PyConfig config;
    PyConfig_InitIsolatedConfig(&config);

    PyWideStringList_Append(&config.warnoptions, L"ignore::UserWarning:pkg_resources");
    PyWideStringList_Append(&config.warnoptions, L"ignore::DeprecationWarning");

    PyStatus status = PyConfig_SetBytesArgv(&config, argc, argv);
    if (PyStatus_Exception(status)) return 1;

    config.module_search_paths_set = 1;

    wchar_t *w_zip = Py_DecodeLocale(zip_path, NULL);
    wchar_t *w_fw  = Py_DecodeLocale(real_fw, NULL);
    wchar_t *w_res = Py_DecodeLocale(real_res, NULL);

    PyWideStringList_Append(&config.module_search_paths, w_zip);
    PyWideStringList_Append(&config.module_search_paths, w_fw);
    PyWideStringList_Append(&config.module_search_paths, w_res);

    PyMem_RawFree(w_zip);
    PyMem_RawFree(w_fw);
    PyMem_RawFree(w_res);

    status = Py_InitializeFromConfig(&config);
    PyConfig_Clear(&config);

    if (PyStatus_Exception(status)) return 1;

    const char *script =
        "import sys, os, builtins, warnings, subprocess\n"
        "warnings.filterwarnings('ignore')\n"
        "\n"
        "exec_dir = os.path.dirname(os.path.realpath(sys.executable))\n"
        "bundle = os.path.abspath(os.path.join(exec_dir, '..'))\n"
        "res = os.path.join(bundle, 'Resources')\n"
        "fw = os.path.join(bundle, 'Frameworks')\n"
        "zip_path = os.path.join(res, 'base_library.zip')\n"
        "\n"
        "for p in [zip_path, fw, res, exec_dir]:\n"
        "    if os.path.exists(p) and p not in sys.path:\n"
        "        sys.path.insert(0, p)\n"
        "\n"
        "try:\n"
        "    import gettext\n"
        "    builtins._ = gettext.translation('deluge', fallback=True).gettext\n"
        "except Exception:\n"
        "    builtins._ = lambda msg: msg\n"
        "\n"
        "def prompt_cli_installer_if_needed():\n"
        "    if sys.platform != 'darwin':\n"
        "        return\n"
        "    flag_file = os.path.expanduser('~/.config/deluge/.mac_cli_prompted')\n"
        "    if os.path.exists(flag_file):\n"
        "        return\n"
        "    try:\n"
        "        os.makedirs(os.path.dirname(flag_file), exist_ok=True)\n"
        "        with open(flag_file, 'w') as f:\n"
        "            f.write('1')\n"
        "        # Ask user if they want to set up command line shortcuts\n"
        "        apple_script = (\n"
        "            'display dialog \"Would you like to install Deluge command-line shortcuts ' \n"
        "            '(deluge, deluged, deluge-web, deluge-console) in /usr/local/bin?\" ' \n"
        "            'buttons {\"Cancel\", \"Install\"} default button \"Install\"'\n"
        "        )\n"
        "        proc = subprocess.run(['osascript', '-e', apple_script], capture_output=True, text=True)\n"
        "        if 'button returned:Install' in proc.stdout:\n"
        "            subprocess.run([sys.executable, '--install-cli'])\n"
        "    except Exception as e:\n"
        "        pass\n"
        "\n"
        "entry_mode = os.path.basename(sys.executable).lower()\n"
        "if 'deluged' in entry_mode:\n"
        "    from deluge.core.daemon_entry import start_daemon\n"
        "    start_daemon()\n"
        "elif 'web' in entry_mode:\n"
        "    from deluge.ui.web.web import start\n"
        "    start()\n"
        "elif 'console' in entry_mode:\n"
        "    from deluge.ui.console.console import start\n"
        "    start()\n"
        "else:\n"
        "    if len(sys.argv) > 1 and sys.argv[1] == '-c':\n"
        "        exec(sys.argv[2])\n"
        "    else:\n"
        "        prompt_cli_installer_if_needed()\n"
        "        import argparse\n"
        "        from deluge.ui.gtk3.gtkui import GtkUI\n"
        "        args = argparse.Namespace(torrents=[])\n"
        "        GtkUI(args).start()\n";

    int result = PyRun_SimpleString(script);
    Py_Finalize();
    return result;
}
