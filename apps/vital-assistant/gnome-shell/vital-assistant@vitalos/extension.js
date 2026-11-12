import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import Meta from 'gi://Meta';
import Shell from 'gi://Shell';

import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import * as QuickSettings from 'resource:///org/gnome/shell/ui/quickSettings.js';

const FocusIface = `
<node>
  <interface name="org.vitalos.AssistantShell">
    <method name="GetFocus">
      <arg type="s" direction="out" name="json"/>
    </method>
  </interface>
</node>`;

const QuickToggle = QuickSettings.QuickToggle;

const FocusService = {
    GetFocus() {
        let title = '';
        let appId = '';
        const win = global.display.get_focus_window();
        if (win) {
            title = win.get_title() || '';
            const tracker = Shell.WindowTracker.get_default();
            const app = tracker.get_window_app(win);
            if (app)
                appId = app.get_id() || '';
        }
        return JSON.stringify({title, app_id: appId});
    },
};

class VitalIndicator extends QuickSettings.SystemIndicator {
    _init(launch) {
        super._init();
        const hebrew = (GLib.getenv('LANG') || '').startsWith('he');
        this._toggle = new QuickToggle({
            title: hebrew ? 'עוזר ויטל' : 'Vital Assistant',
            iconName: 'system-search-symbolic',
            toggleMode: false,
        });
        this._toggle.connect('clicked', () => launch());
        this.quickSettingsItems.push(this._toggle);
    }
}

export default class VitalAssistantExtension extends Extension {
    enable() {
        this._settings = this.getSettings();
        this._last = 0;
        this._nameId = 0;
        this._impl = null;
        Main.wm.addKeybinding(
            'overlay-key',
            this._settings,
            Meta.KeyBindingFlags.IGNORE_AUTOREPEAT,
            Shell.ActionMode.NORMAL | Shell.ActionMode.OVERVIEW,
            () => this._launch()
        );
        this._indicator = new VitalIndicator(() => this._launch());
        Main.panel.statusArea.quickSettings.addExternalIndicator(this._indicator);
        this._nameId = Gio.bus_own_name(
            Gio.BusType.SESSION,
            'org.vitalos.AssistantShell',
            Gio.BusNameOwnerFlags.REPLACE,
            connection => {
                this._impl = Gio.DBusExportedObject.wrapJSObject(FocusIface, FocusService);
                this._impl.export(connection, '/org/vitalos/AssistantShell');
            },
            null,
            null
        );
    }

    disable() {
        Main.wm.removeKeybinding('overlay-key');
        if (this._indicator) {
            this._indicator.destroy();
            this._indicator = null;
        }
        if (this._impl) {
            this._impl.unexport();
            this._impl = null;
        }
        if (this._nameId) {
            Gio.bus_unown_name(this._nameId);
            this._nameId = 0;
        }
        this._settings = null;
    }

    _launch() {
        const now = GLib.get_monotonic_time();
        if (now - this._last < 400000)
            return;
        this._last = now;
        try {
            Gio.Subprocess.new(['vital-assistant', '--overlay'], Gio.SubprocessFlags.NONE);
        } catch (error) {
            log(`Vital Assistant failed to launch: ${error}`);
        }
    }
}
