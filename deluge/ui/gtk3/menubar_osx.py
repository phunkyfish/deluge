#
# Copyright (C) 2007-2009 Andrew Resch <andrewresch@gmail.com>
#
# This file is part of Deluge and is licensed under GNU General Public License 3.0, or later, with
# the additional special exception to link portions of this program with the OpenSSL library.
# See LICENSE for more details.
#

import os
import subprocess
import sys

from gi.repository import Gdk, Gio, GLib, Gtk

import deluge.component as component
from deluge.configmanager import ConfigManager
from deluge.ui.client import client

macos_main_window_accelmap = {
    '<Deluge-MainWindow>/File/Add Torrent': '<Meta>o',
    '<Deluge-MainWindow>/File/Create Torrent': '<Meta>n',
    '<Deluge-MainWindow>/File/Quit & Shutdown Daemon': '<Meta><Shift>q',
    '<Deluge-MainWindow>/File/Quit': '<Meta>q',
    '<Deluge-MainWindow>/Edit/Preferences': '<Meta>comma',
    '<Deluge-MainWindow>/Edit/Connection Manager': '<Meta>m',
    '<Deluge-MainWindow>/View/Find ...': '<Meta>f',
    '<Deluge-MainWindow>/Help/FAQ': '<Meta>question',
}

_current_dark_mode_state = None


def is_macos_dark_mode():
    if sys.platform != 'darwin':
        return False
    try:
        res = subprocess.run(
            ['defaults', 'read', '-g', 'AppleInterfaceStyle'],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        if res.returncode == 0 and res.stdout.strip().lower() == 'dark':
            return True
    except Exception:
        pass
    return False


def apply_dark_mode(enabled, force=False):
    global _current_dark_mode_state
    if _current_dark_mode_state != enabled or force:
        _current_dark_mode_state = enabled
        settings = Gtk.Settings.get_default()
        if settings:
            settings.set_property('gtk-application-prefer-dark-theme', enabled)

        try:
            config = ConfigManager('gtk3ui.conf')
            config['choose_theme'] = enabled
            config.save()
        except Exception:
            pass


def sync_macos_theme(force=False):
    system_dark = is_macos_dark_mode()
    apply_dark_mode(system_dark, force=force)
    return True


def ensure_dialog_focus(main_window):
    for win in Gtk.Window.list_toplevels():
        if isinstance(win, Gtk.Window) and win.is_visible() and win != main_window:
            win.set_transient_for(main_window)
            if isinstance(win, Gtk.Dialog):
                win.set_modal(True)

            current_time = Gdk.CURRENT_TIME
            win.present_with_time(current_time)

            gdk_win = win.get_window()
            if gdk_win:
                gdk_win.focus(current_time)
                gdk_win.raise_()


def hide_and_override_preferences_theme(gtkui):
    try:
        pref_builder = gtkui.preferences.builder
        theme_widgets = ['chk_use_dark_theme', 'chk_dark_theme', 'box_theme', 'frame_theme']
        for widget_id in theme_widgets:
            widget = pref_builder.get_object(widget_id)
            if widget:
                widget.set_no_show_all(True)
                widget.hide()

        pref_dialog = pref_builder.get_object('preferences_dialog')
        if pref_dialog and not getattr(pref_dialog, '_theme_hook_connected', False):
            pref_dialog.connect('show', lambda w: GLib.idle_add(lambda: sync_macos_theme(force=True)))
            pref_dialog.connect('hide', lambda w: GLib.idle_add(lambda: sync_macos_theme(force=True)))
            pref_dialog._theme_hook_connected = True
    except Exception:
        pass


def install_cli_tools_action(action, parameter, gtkui):
    try:
        exec_dir = os.path.dirname(os.path.realpath(sys.executable))

        cmd_map = {
            'deluge': 'Deluge',
            'deluge-gtk': 'deluge-gtk',
            'deluged': 'deluged',
            'deluge-web': 'deluge-web',
            'deluge-console': 'deluge-console',
        }

        needs_update = False
        for cmd, binary in cmd_map.items():
            src = os.path.join(exec_dir, binary)
            dst = os.path.join('/usr/local/bin', cmd)

            if not os.path.islink(dst) or os.path.realpath(dst) != src:
                needs_update = True
                break

        if not needs_update:
            dialog = Gtk.MessageDialog(
                transient_for=gtkui.mainwindow.window,
                flags=0,
                message_type=Gtk.MessageType.INFO,
                buttons=Gtk.ButtonsType.OK,
                text=_('CLI Tools Already Installed'),
            )
            dialog.format_secondary_text(
                _('All command-line shortcuts in /usr/local/bin are up to date.')
            )
            ensure_dialog_focus(gtkui.mainwindow.window)
            dialog.run()
            dialog.destroy()
            return

        ln_cmds = []
        for cmd, binary in cmd_map.items():
            src = os.path.join(exec_dir, binary)
            dst = os.path.join('/usr/local/bin', cmd)
            ln_cmds.append(f"ln -sf '{src}' '{dst}'")

        shell_cmd = 'mkdir -p /usr/local/bin && ' + ' && '.join(ln_cmds)
        ascript = f'do shell script "{shell_cmd}" with administrator privileges'

        res = subprocess.run(
            ['osascript', '-e', ascript], capture_output=True, text=True
        )

        if res.returncode == 0:
            title = _('CLI Tools Installed')
            msg = _(
                'Command-line shortcuts (deluge, deluged, deluge-web, deluge-console) '
                'were successfully linked in /usr/local/bin.'
            )
            msg_type = Gtk.MessageType.INFO
        else:
            title = _('Installation Cancelled')
            msg = _('Installation was cancelled or failed to acquire admin privileges.')
            msg_type = Gtk.MessageType.WARNING

        dialog = Gtk.MessageDialog(
            transient_for=gtkui.mainwindow.window,
            flags=0,
            message_type=msg_type,
            buttons=Gtk.ButtonsType.OK,
            text=title,
        )
        dialog.format_secondary_text(msg)
        ensure_dialog_focus(gtkui.mainwindow.window)
        dialog.run()
        dialog.destroy()

    except Exception as e:
        dialog = Gtk.MessageDialog(
            transient_for=gtkui.mainwindow.window,
            flags=0,
            message_type=Gtk.MessageType.ERROR,
            buttons=Gtk.ButtonsType.OK,
            text=_('Error'),
        )
        dialog.format_secondary_text(str(e))
        ensure_dialog_focus(gtkui.mainwindow.window)
        dialog.run()
        dialog.destroy()


def menubar_osx(gtkui, app):
    GLib.idle_add(lambda: sync_macos_theme(force=True))
    GLib.timeout_add_seconds(5, sync_macos_theme)

    for accel_path, accelerator in macos_main_window_accelmap.items():
        accel_key, accel_mods = Gtk.accelerator_parse(accelerator)
        Gtk.AccelMap.change_entry(accel_path, accel_key, accel_mods, True)

    main_builder = gtkui.mainwindow.get_builder()
    menubar = main_builder.get_object('menubar')

    if menubar:
        menubar.hide()

    def trigger_widget_action(widget_name):
        obj = main_builder.get_object(widget_name)
        if obj:
            obj.emit('activate')

    def open_preferences_action(a, p):
        if hasattr(gtkui, 'preferences'):
            gtkui.preferences.show()
            hide_and_override_preferences_theme(gtkui)
            GLib.idle_add(lambda: sync_macos_theme(force=True))

    def quit_action(a, p):
        # Fire Deluge's standard shutdown sequence via Twisted reactor
        from twisted.internet import reactor
        reactor.callLater(0, reactor.fireSystemEvent, 'gtkui_close')

    def trigger_ui_action(action_name):
        if action_name == 'add_torrent':
            if client.connected():
                gtkui.addtorrentdialog.show()
        elif action_name == 'create_torrent':
            from deluge.ui.gtk3.createtorrentdialog import CreateTorrentDialog
            CreateTorrentDialog().show()
        elif action_name == 'select_all':
            if hasattr(gtkui.torrentview, 'treeview'):
                gtkui.torrentview.treeview.get_selection().select_all()
        elif action_name == 'pause_all':
            if client.connected():
                client.core.pause_torrents([])
        elif action_name == 'resume_all':
            if client.connected():
                client.core.resume_torrents([])

    def toggle_dark_mode_action(action, parameter):
        global _current_dark_mode_state
        new_state = not bool(_current_dark_mode_state)
        apply_dark_mode(new_state, force=True)

    connection_dependent_actions = {
        'add_torrent',
        'pause_all',
        'resume_all',
        'select_all',
    }

    registered_actions = {}

    action_map = {
        'about': lambda a, p: trigger_widget_action('menuitem_about'),
        'preferences': open_preferences_action,
        'connection_manager': lambda a, p: trigger_widget_action('menuitem_connectionmanager'),
        'toggle_dark_mode': toggle_dark_mode_action,
        'quit': quit_action,
        'install_cli': lambda a, p: install_cli_tools_action(a, p, gtkui),
        'add_torrent': lambda a, p: trigger_ui_action('add_torrent'),
        'create_torrent': lambda a, p: trigger_ui_action('create_torrent'),
        'select_all': lambda a, p: trigger_ui_action('select_all'),
        'pause_all': lambda a, p: trigger_ui_action('pause_all'),
        'resume_all': lambda a, p: trigger_ui_action('resume_all'),
        'homepage': lambda a, p: trigger_widget_action('menuitem_homepage'),
        'faq': lambda a, p: trigger_widget_action('menuitem_faq'),
    }

    def wrap_action_callback(callback):
        def wrapped(a, p):
            callback(a, p)
            GLib.idle_add(lambda: ensure_dialog_focus(gtkui.mainwindow.window))
        return wrapped

    for action_name, callback in action_map.items():
        if not app.has_action(action_name):
            act = Gio.SimpleAction.new(action_name, None)
            act.connect('activate', wrap_action_callback(callback))
            app.add_action(act)
            registered_actions[action_name] = act

    def update_action_states():
        is_connected = client.connected()
        for act_name in connection_dependent_actions:
            if act_name in registered_actions:
                registered_actions[act_name].set_enabled(is_connected)
        return True

    GLib.timeout_add_seconds(2, update_action_states)

    def setup_app_menus():
        # Register main window after startup windows have initialized
        if hasattr(gtkui.mainwindow, 'window'):
            app.add_window(gtkui.mainwindow.window)

        config = ConfigManager('gtk3ui.conf')

        # Restore Connection Manager display on startup if configured
        if not config['standalone'] and config.get('show_connection_manager_on_start'):
            if hasattr(gtkui, 'connectionmanager'):
                gtkui.connectionmanager.show()

        # Build App Menu
        app_menu = Gio.Menu()

        section_about = Gio.Menu()
        section_about.append(_('About Deluge'), 'app.about')
        app_menu.append_section(None, section_about)

        section_prefs = Gio.Menu()
        section_prefs.append(_('Preferences...'), 'app.preferences')

        if not config['standalone']:
            section_prefs.append(_('Connection Manager'), 'app.connection_manager')

        section_prefs.append(_('Toggle Dark Mode'), 'app.toggle_dark_mode')
        app_menu.append_section(None, section_prefs)

        section_cli = Gio.Menu()
        section_cli.append(_('Install Command Line Tools...'), 'app.install_cli')
        app_menu.append_section(None, section_cli)

        section_quit = Gio.Menu()
        section_quit.append(_('Quit Deluge'), 'app.quit')
        app_menu.append_section(None, section_quit)

        app.set_app_menu(app_menu)

        # Build Menubar
        full_menubar = Gio.Menu()

        file_menu = Gio.Menu()
        file_menu.append(_('Add Torrent...'), 'app.add_torrent')
        file_menu.append(_('Create Torrent...'), 'app.create_torrent')
        full_menubar.append_submenu(_('File'), file_menu)

        edit_menu = Gio.Menu()
        edit_menu.append(_('Select All'), 'app.select_all')
        full_menubar.append_submenu(_('Edit'), edit_menu)

        view_menu = Gio.Menu()
        view_menu.append(_('Pause All Torrents'), 'app.pause_all')
        view_menu.append(_('Resume All Torrents'), 'app.resume_all')
        full_menubar.append_submenu(_('View'), view_menu)

        help_menu = Gio.Menu()
        help_menu.append(_('Homepage'), 'app.homepage')
        help_menu.append(_('FAQ'), 'app.faq')
        full_menubar.append_submenu(_('Help'), help_menu)

        app.set_menubar(full_menubar)
        return False

    # Defer setting up app window and menus until GTK main loop processes startup windowing
    GLib.idle_add(setup_app_menus)
