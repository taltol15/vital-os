"""Overlay, settings, and confirmation UI for Vital Assistant.

The windows call the same core as the terminal. Context chips start off.
A state-changing action stays on screen until Confirm is pressed.
"""

from __future__ import annotations

import os
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Gdk", "4.0")
from gi.repository import Adw, Gdk, GLib, Gtk

from vital_actions import confirmation_text, plan_action
from vital_assistant import AssistantError, Settings, keystore_for, load_settings, save_user_settings
from vital_context import Consent
from vital_core import approve_action, clear_history, iter_answer
from vital_i18n import translator


def css_path() -> Path | None:
    candidates = [
        Path("/usr/share/vitalos/assistant/assistant.css"),
        Path(__file__).resolve().parent / "assistant.css",
    ]
    for path in candidates:
        if path.is_file():
            return path
    return None


def apply_css() -> None:
    path = css_path()
    if path is None:
        return
    display = Gdk.Display.get_default()
    if display is None:
        return
    provider = Gtk.CssProvider()
    provider.load_from_path(str(path))
    Gtk.StyleContext.add_provider_for_display(display, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)


def language_preference() -> str:
    forced = os.environ.get("VITAL_ASSISTANT_LANGUAGE", "").strip()
    if forced:
        return forced
    return load_settings().language


def catalog():
    text = translator(language_preference())
    if text.rtl:
        Gtk.Widget.set_default_direction(Gtk.TextDirection.RTL)
    else:
        Gtk.Widget.set_default_direction(Gtk.TextDirection.LTR)
    return text


class OverlayWindow(Gtk.ApplicationWindow):
    def __init__(self, app: Adw.Application) -> None:
        super().__init__(application=app, title="Vital Assistant")
        self.set_decorated(False)
        self.set_default_size(740, 560)
        self.set_resizable(True)
        self.add_css_class("vital-overlay")
        self.settings = load_settings()
        self.t = catalog()
        self.set_title(self.t("app-name"))
        self._plan = None
        self._suggestion = None
        self._busy = False
        self._files: list[str] = []

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        root.set_margin_top(18)
        root.set_margin_bottom(18)
        root.set_margin_start(18)
        root.set_margin_end(18)
        root.add_css_class("vital-card")

        header = Gtk.Box(spacing=12)
        title = Gtk.Label(label=self.t("app-name"), xalign=0)
        title.add_css_class("title-1")
        title.add_css_class("vital-accent")
        self.provider_label = Gtk.Label(label="", xalign=1, hexpand=True)
        self.provider_label.add_css_class("vital-provider")
        header.append(title)
        header.append(self.provider_label)

        self.entry = Gtk.Entry()
        self.entry.add_css_class("vital-entry")
        self.entry.props.placeholder_text = self.t("overlay-placeholder")
        self.entry.connect("activate", lambda *_a: self.submit())

        hint = Gtk.Label(label=self.t("overlay-hint"), xalign=0, wrap=True)
        hint.add_css_class("vital-muted")

        self.chips = Gtk.Box(spacing=8)
        self.file_chip = self._chip("files", self.t("context-files"))
        self.window_chip = self._chip("window", self.t("context-window"))
        self.clipboard_chip = self._chip("clipboard", self.t("context-clipboard"))
        self.screenshot_chip = self._chip("screenshot", self.t("context-screenshot"))
        for chip, offered in (
            (self.file_chip, self.settings.offer_files),
            (self.window_chip, self.settings.offer_window),
            (self.clipboard_chip, self.settings.offer_clipboard),
            (self.screenshot_chip, self.settings.offer_screenshot),
        ):
            chip.set_visible(offered)
            self.chips.append(chip)

        self.disclosure = Gtk.Label(label="", xalign=0, wrap=True)
        self.disclosure.add_css_class("vital-faint")

        self.answer = Gtk.Label(xalign=0, yalign=0, wrap=True, selectable=True, hexpand=True)
        self.answer.add_css_class("vital-muted")
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrolled.set_vexpand(True)
        scrolled.set_min_content_height(180)
        scrolled.set_child(self.answer)

        self.confirm_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.confirm_box.add_css_class("card")
        self.confirm_title = Gtk.Label(label=self.t("confirm-title"), xalign=0)
        self.confirm_title.add_css_class("title-4")
        self.confirm_body = Gtk.Label(xalign=0, wrap=True, selectable=True)
        self.confirm_body.add_css_class("vital-command")
        buttons = Gtk.Box(spacing=8)
        self.cancel_button = Gtk.Button(label=self.t("cancel"))
        self.cancel_button.connect("clicked", lambda *_a: self._reject())
        self.confirm_button = Gtk.Button(label=self.t("confirm"))
        self.confirm_button.add_css_class("suggested-action")
        self.confirm_button.connect("clicked", lambda *_a: self._accept())
        buttons.append(self.cancel_button)
        buttons.append(self.confirm_button)
        self.confirm_box.append(self.confirm_title)
        self.confirm_box.append(self.confirm_body)
        self.confirm_box.append(buttons)
        self.confirm_box.set_visible(False)

        actions = Gtk.Box(spacing=8)
        ask = Gtk.Button(label=self.t("ask"))
        ask.add_css_class("suggested-action")
        ask.connect("clicked", lambda *_a: self.submit())
        settings_button = Gtk.Button(label=self.t("settings"))
        settings_button.connect("clicked", lambda *_a: self._open_settings())
        actions.append(ask)
        actions.append(settings_button)

        root.append(header)
        root.append(hint)
        root.append(self.entry)
        root.append(self.chips)
        root.append(self.disclosure)
        root.append(scrolled)
        root.append(self.confirm_box)
        root.append(actions)
        self.set_child(root)

        keys = Gtk.EventControllerKey()
        keys.connect("key-pressed", self._on_key)
        self.add_controller(keys)
        self.entry.grab_focus()
        self._prepare_demo()

    def _chip(self, name: str, label: str) -> Gtk.ToggleButton:
        button = Gtk.ToggleButton(label=label)
        button.add_css_class("vital-chip")
        button.set_name(name)
        if name == "files":
            button.connect("toggled", self._pick_files)
        return button

    def _on_key(self, _controller, keyval, _code, _state) -> bool:
        if keyval == Gdk.KEY_Escape:
            if self.confirm_box.get_visible():
                self._reject()
            else:
                self.close()
            return True
        return False

    def _prepare_demo(self) -> None:
        demo = os.environ.get("VITAL_ASSISTANT_DEMO", "")
        if demo == "answer":
            self.entry.set_text("How do I delete an empty folder?")
            self.submit()
        elif demo == "context":
            for chip in (self.file_chip, self.window_chip, self.clipboard_chip, self.screenshot_chip):
                chip.set_visible(True)

    def _open_settings(self) -> None:
        window = SettingsWindow(self.get_application())
        window.present()

    def _pick_files(self, button: Gtk.ToggleButton) -> None:
        if not button.get_active():
            self._files = []
            button.set_label(self.t("context-files"))
            return
        dialog = Gtk.FileDialog()
        dialog.open_multiple(self, None, self._files_chosen)

    def _files_chosen(self, dialog: Gtk.FileDialog, result) -> None:
        try:
            files = dialog.open_multiple_finish(result)
        except GLib.Error:
            self.file_chip.set_active(False)
            return
        self._files = []
        if files is not None:
            index = 0
            while index < files.get_n_items():
                item = files.get_item(index)
                path = item.get_path() if item is not None and hasattr(item, "get_path") else None
                if path:
                    self._files.append(path)
                index += 1
        self.file_chip.set_label(self.t("files-chip", count=len(self._files)))

    def submit(self) -> None:
        if self._busy:
            return
        question = self.entry.get_text().strip()
        if not question:
            return
        self._busy = True
        self._plan = None
        self._suggestion = None
        self.confirm_box.set_visible(False)
        self.answer.set_text("")
        consent = Consent(
            files=tuple(self._files) if self.file_chip.get_active() else (),
            window=self.window_chip.get_active(),
            clipboard=self.clipboard_chip.get_active(),
            screenshot=self.screenshot_chip.get_active(),
            allow_remote=False,
        )
        payload: dict = {}
        if consent.clipboard:
            payload["clipboard"] = _clipboard_text(self)
        if consent.window:
            payload.update(_focus_payload())
        if consent.screenshot:
            path = _capture_screenshot()
            if path:
                payload["screenshot_path"] = path
        self._start_answer(question, consent, payload)

    def _start_answer(self, question: str, consent: Consent, payload: dict) -> None:
        holder: dict = {"events": None, "error": None}

        def work() -> None:
            try:
                holder["events"] = list(
                    iter_answer(
                        question,
                        self.settings,
                        keystore_for(self.settings),
                        consent=consent,
                        payload=payload,
                        mode="answer",
                    )
                )
            except AssistantError as exc:
                holder["error"] = str(exc)

        def finish() -> bool:
            self._busy = False
            if holder["error"]:
                self.answer.set_text(holder["error"])
                return False
            self._apply_events(holder["events"] or [])
            return False

        if os.environ.get("VITAL_ASSISTANT_DEMO"):
            work()
            finish()
            return
        import threading

        threading.Thread(target=lambda: (work(), GLib.idle_add(finish)), daemon=True).start()

    def _apply_events(self, events: list[dict]) -> None:
        text = []
        for event in events:
            kind = event.get("event")
            if kind == "provider":
                self.provider_label.set_text(str(event.get("label") or ""))
            elif kind == "disclosure":
                notes = " ".join(event.get("notes") or [])
                shown = str(event.get("text") or "")
                if notes:
                    shown = shown + " " + notes
                self.disclosure.set_text(shown)
            elif kind == "token":
                text.append(str(event.get("text") or ""))
            elif kind == "suggestion":
                self._suggestion = event
            elif kind == "confirm":
                self._show_plan(event.get("plan") or {})
            elif kind == "error":
                text.append(str(event.get("message") or ""))
            elif kind == "status":
                text.append("\n" + str(event.get("output") or ""))
        shown = "".join(text).strip()
        if self._suggestion:
            explanation = str(self._suggestion.get("explanation") or "").strip()
            command = str(self._suggestion.get("command") or "").strip()
            shown = explanation or shown
            if command:
                shown = (shown + "\n\n" + command + "\n" + self.t("not-executed")).strip()
        if shown:
            self.answer.set_text(shown)

    def _show_plan(self, raw: dict) -> None:
        try:
            plan = plan_action(str(raw.get("name", "")), raw.get("args") if isinstance(raw.get("args"), dict) else {})
        except Exception as exc:  # noqa: BLE001 - show the refusal in the panel
            self.confirm_body.set_text(str(exc))
            self.confirm_box.set_visible(True)
            self.cancel_button.grab_focus()
            return
        self._plan = plan
        self.confirm_body.set_text(confirmation_text(plan))
        self.confirm_box.set_visible(True)
        self.cancel_button.grab_focus()

    def _reject(self) -> None:
        plan = self._plan
        self.confirm_box.set_visible(False)
        self._plan = None
        if plan is not None:
            try:
                approve_action(plan.to_dict(), False)
            except Exception:
                pass
        self.disclosure.set_text(self.t("not-executed"))

    def _accept(self) -> None:
        plan = self._plan
        if plan is None:
            return
        try:
            result = approve_action(plan.to_dict(), True)
        except Exception as exc:  # noqa: BLE001
            self.confirm_body.set_text(str(exc))
            return
        self.confirm_box.set_visible(False)
        self._plan = None
        current = self.answer.get_text()
        self.answer.set_text((current + "\n" + result.get("output", "")).strip())

    def show_plan_preview(self, plan) -> None:
        self._plan = plan
        self.provider_label.set_text(self.t("provider-local"))
        self.confirm_body.set_text(confirmation_text(plan))
        self.confirm_box.set_visible(True)
        self.disclosure.set_text(self.t("confirm-polkit") if plan.privileged else "")
        self.cancel_button.grab_focus()


class SettingsWindow(Adw.PreferencesWindow):
    def __init__(self, app: Gtk.Application) -> None:
        super().__init__(application=app, title="Vital Assistant")
        self.set_default_size(760, 980)
        self.settings = load_settings()
        self.t = catalog()
        self.set_title(self.t("settings"))
        self._build()

    def _build(self) -> None:
        page = Adw.PreferencesPage(title=self.t("settings"))
        self.add(page)

        connection = Adw.PreferencesGroup(title=self.t("connection"), description=self.t("key-stored"))
        providers = Gtk.StringList.new(
            [
                self.t("provider-auto"),
                self.t("provider-grok"),
                self.t("provider-openai"),
                self.t("provider-ollama"),
                self.t("provider-local"),
            ]
        )
        self.provider_row = Adw.ComboRow(title=self.t("provider"), model=providers)
        self.provider_row.set_selected(_provider_index(self.settings.provider))
        self.model_row = Adw.EntryRow(title=self.t("model"))
        self.model_row.set_text(self.settings.model)
        self.base_row = Adw.EntryRow(title=self.t("base-url"))
        self.base_row.set_text(self.settings.base_url)
        self.key_row = Adw.PasswordEntryRow(title=self.t("api-key"))
        devices = Gtk.StringList.new([self.t("device-auto"), self.t("device-cpu"), self.t("device-gpu")])
        self.device_row = Adw.ComboRow(title=self.t("local-device"), model=devices)
        self.device_row.set_selected({"auto": 0, "cpu": 1, "gpu": 2}.get(self.settings.local_device, 0))
        save_row = Adw.ActionRow(title=self.t("save"))
        save_button = Gtk.Button(label=self.t("save"))
        save_button.add_css_class("suggested-action")
        save_button.set_valign(Gtk.Align.CENTER)
        save_button.connect("clicked", self._save)
        save_row.add_suffix(save_button)
        remove_row = Adw.ActionRow(title=self.t("key-remove"))
        remove_button = Gtk.Button(label=self.t("key-remove"))
        remove_button.set_valign(Gtk.Align.CENTER)
        remove_button.connect("clicked", self._remove_key)
        remove_row.add_suffix(remove_button)
        self.status_row = Adw.ActionRow(title=self.t("key-missing"))
        for row in (
            self.provider_row,
            self.model_row,
            self.base_row,
            self.key_row,
            self.device_row,
            save_row,
            remove_row,
            self.status_row,
        ):
            connection.add(row)
        page.add(connection)

        appearance = Adw.PreferencesGroup(title=self.t("appearance"))
        languages = Gtk.StringList.new(
            [self.t("language-system"), self.t("language-en"), self.t("language-he")]
        )
        self.language_row = Adw.ComboRow(title=self.t("language"), model=languages)
        self.language_row.set_selected({"system": 0, "en": 1, "he": 2}.get(self.settings.language, 0))
        self.hotkey_row = Adw.EntryRow(title=self.t("hotkey"))
        self.hotkey_row.set_text(self.settings.hotkey)
        hotkey_help = Adw.ActionRow(title=self.t("hotkey-help"))
        appearance.add(self.language_row)
        appearance.add(self.hotkey_row)
        appearance.add(hotkey_help)
        page.add(appearance)

        permissions = Adw.PreferencesGroup(title=self.t("permissions"), description=self.t("actions-help"))
        self.actions_row = Adw.SwitchRow(title=self.t("actions"), subtitle=self.t("action-log"))
        self.actions_row.set_active(self.settings.actions_enabled)
        self.shell_row = Adw.SwitchRow(title=self.t("shell-hook"), subtitle=self.t("shell-hook-help"))
        self.shell_row.set_active(self.settings.shell_hook)
        self.context_row = Adw.SwitchRow(title=self.t("send-context"))
        self.context_row.set_active(self.settings.send_context)
        permissions.add(self.actions_row)
        permissions.add(self.shell_row)
        permissions.add(self.context_row)
        page.add(permissions)

        context = Adw.PreferencesGroup(title=self.t("context"), description=self.t("context-help"))
        self.offer_files = Adw.SwitchRow(title=self.t("offer-files"))
        self.offer_window = Adw.SwitchRow(title=self.t("offer-window"))
        self.offer_clipboard = Adw.SwitchRow(title=self.t("offer-clipboard"))
        self.offer_screenshot = Adw.SwitchRow(title=self.t("offer-screenshot"))
        self.offer_files.set_active(self.settings.offer_files)
        self.offer_window.set_active(self.settings.offer_window)
        self.offer_clipboard.set_active(self.settings.offer_clipboard)
        self.offer_screenshot.set_active(self.settings.offer_screenshot)
        for row in (self.offer_files, self.offer_window, self.offer_clipboard, self.offer_screenshot):
            context.add(row)
        page.add(context)

        history = Adw.PreferencesGroup(title=self.t("history"), description=self.t("history-help"))
        wipe = Adw.ActionRow(title=self.t("wipe-history"), subtitle=self.t("wipe-history-body"))
        wipe_button = Gtk.Button(label=self.t("wipe-history"))
        wipe_button.add_css_class("destructive-action")
        wipe_button.set_valign(Gtk.Align.CENTER)
        wipe_button.connect("clicked", self._wipe)
        wipe.add_suffix(wipe_button)
        history.add(wipe)
        page.add(history)

    def _selected_provider(self) -> str:
        return ["auto", "grok", "openai", "ollama", "local"][self.provider_row.get_selected()]

    def _save(self, _button: Gtk.Button) -> None:
        from vital_assistant import valid_hotkey

        updated = Settings(**{field: getattr(self.settings, field) for field in Settings.__dataclass_fields__})
        updated.provider = self._selected_provider()
        updated.model = self.model_row.get_text().strip()
        updated.base_url = self.base_row.get_text().strip()
        updated.local_device = ["auto", "cpu", "gpu"][self.device_row.get_selected()]
        updated.language = ["system", "en", "he"][self.language_row.get_selected()]
        hotkey = self.hotkey_row.get_text().strip()
        if not valid_hotkey(hotkey):
            self.status_row.set_title(self.t("hotkey"))
            return
        updated.hotkey = hotkey
        updated.actions_enabled = self.actions_row.get_active()
        updated.shell_hook = self.shell_row.get_active()
        updated.send_context = self.context_row.get_active()
        updated.offer_files = self.offer_files.get_active()
        updated.offer_window = self.offer_window.get_active()
        updated.offer_clipboard = self.offer_clipboard.get_active()
        updated.offer_screenshot = self.offer_screenshot.get_active()
        secret = self.key_row.get_text().strip()
        try:
            if secret and updated.provider in {"grok", "openai", "auto"}:
                account = "openai" if updated.provider == "openai" else "grok"
                keystore_for(Settings(provider=account)).store(account, secret)
            save_user_settings(updated)
            _write_hotkey(updated.hotkey)
        except AssistantError as exc:
            self.status_row.set_title(str(exc))
            return
        self.key_row.set_text("")
        self.settings = updated
        self.status_row.set_title(self.t("saved"))

    def _remove_key(self, _button: Gtk.Button) -> None:
        provider = self._selected_provider()
        account = "openai" if provider == "openai" else "grok"
        try:
            keystore_for(Settings(provider=account)).delete(account)
        except AssistantError as exc:
            self.status_row.set_title(str(exc))
            return
        self.status_row.set_title(self.t("key-missing"))

    def _wipe(self, _button: Gtk.Button) -> None:
        dialog = Adw.AlertDialog(heading=self.t("wipe-history"), body=self.t("wipe-history-body"))
        dialog.add_response("cancel", self.t("cancel"))
        dialog.add_response("wipe", self.t("wipe-history"))
        dialog.set_response_appearance("wipe", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.set_default_response("cancel")
        dialog.set_close_response("cancel")

        def respond(_dialog, response: str) -> None:
            if response != "wipe":
                return
            clear_history()
            self.status_row.set_title(self.t("history-cleared"))

        dialog.connect("response", respond)
        dialog.present(self)


class ConfirmWindow(Gtk.ApplicationWindow):
    """The confirmation panel, using the same text the overlay shows."""

    def __init__(self, app: Gtk.Application) -> None:
        super().__init__(application=app, title="Vital Assistant")
        self.set_default_size(740, 460)
        self.add_css_class("vital-overlay")
        text = catalog()
        plan = plan_action("apps.install", {"source": "apt", "name": "vim"})
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        root.set_margin_top(20)
        root.set_margin_bottom(20)
        root.set_margin_start(20)
        root.set_margin_end(20)
        root.add_css_class("vital-card")
        title = Gtk.Label(label=text("confirm-title"), xalign=0)
        title.add_css_class("title-2")
        title.add_css_class("vital-accent")
        body = Gtk.Label(label=confirmation_text(plan), xalign=0, wrap=True, selectable=True)
        body.add_css_class("vital-muted")
        buttons = Gtk.Box(spacing=8)
        cancel = Gtk.Button(label=text("cancel"))
        confirm = Gtk.Button(label=text("confirm"))
        confirm.add_css_class("suggested-action")
        buttons.append(cancel)
        buttons.append(confirm)
        root.append(title)
        root.append(body)
        root.append(buttons)
        self.set_child(root)
        cancel.grab_focus()


def _provider_index(provider: str) -> int:
    return {"auto": 0, "grok": 1, "openai": 2, "openai-compatible": 2, "ollama": 3, "local": 4}.get(provider, 1)


def _write_hotkey(hotkey: str) -> None:
    import subprocess

    value = f"['{hotkey}']"
    subprocess.run(
        ["gsettings", "set", "org.gnome.shell.extensions.vital-assistant", "overlay-key", value],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _clipboard_text(widget: Gtk.Widget) -> str:
    # GTK4 clipboard reads are async. A synchronous display clipboard is not
    # available; the chip still records consent and the async read fills this
    # only when a previous read completed. The portal/session path below is
    # best-effort and never raises into the question.
    try:
        import subprocess

        completed = subprocess.run(
            ["wl-paste", "-n"],
            check=False,
            text=True,
            capture_output=True,
            timeout=1,
        )
        if completed.returncode == 0:
            return completed.stdout[:8000]
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return ""


def _focus_payload() -> dict:
    try:
        import json
        import dbus

        bus = dbus.SessionBus()
        obj = bus.get_object("org.vitalos.AssistantShell", "/org/vitalos/AssistantShell")
        raw = obj.GetFocus(dbus_interface="org.vitalos.AssistantShell", timeout=1.0)
        data = json.loads(str(raw))
    except Exception:
        return {}
    if not isinstance(data, dict):
        return {}
    return {"window_title": str(data.get("title") or ""), "window_app": str(data.get("app_id") or "")}


def _capture_screenshot() -> str:
    """Ask the screenshot portal. Return a local image path, or nothing.

    The portal's own dialog is the second consent. A handle without a file
    URI is not treated as an image, so nothing is attached.
    """

    try:
        import dbus
        from dbus.mainloop.glib import DBusGMainLoop
    except Exception:
        return ""
    found = {"path": ""}

    def response(_response, results) -> None:
        uri = ""
        try:
            uri = str(results.get("uri") or "")
        except Exception:
            uri = ""
        if uri.startswith("file://"):
            found["path"] = uri[7:]
        loop.quit()

    try:
        DBusGMainLoop(set_as_default=True)
        loop = GLib.MainLoop()
        bus = dbus.SessionBus()
        portal = bus.get_object("org.freedesktop.portal.Desktop", "/org/freedesktop/portal/desktop")
        request = portal.Screenshot(
            "",
            {"interactive": True},
            dbus_interface="org.freedesktop.portal.Screenshot",
            timeout=2,
        )
        bus.add_signal_receiver(
            response,
            signal_name="Response",
            dbus_interface="org.freedesktop.portal.Request",
            path=str(request),
        )
        GLib.timeout_add(2500, loop.quit)
        loop.run()
    except Exception:
        return ""
    path = found["path"]
    if path and Path(path).is_file():
        return path
    return ""
