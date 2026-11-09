"""English and Hebrew strings for Vital Assistant.

The catalogs live in the package so the interface works before gettext
locale packages are installed. Hebrew uses GTK's RTL direction.
"""

from __future__ import annotations

import os

STRINGS: dict[str, dict[str, str]] = {
    "en": {
        "app-name": "Vital Assistant",
        "overlay-placeholder": "Ask Vital OS…",
        "overlay-hint": "Enter asks. Esc closes. Nothing on this system changes until you confirm it.",
        "settings": "Settings",
        "ask": "Ask",
        "cancel": "Cancel",
        "confirm": "Confirm",
        "run": "Run",
        "close": "Close",
        "provider": "Provider",
        "provider-answering": "Answering with {provider}",
        "disclosure-none": "No personal context is included. Answering with {provider}.",
        "disclosure-send": "This request includes {items}. It goes to {destination}.",
        "dest-local": "this computer only",
        "context-files": "Files",
        "context-window": "Active window",
        "context-clipboard": "Clipboard",
        "context-screenshot": "Screenshot",
        "files-chip": "Files ({count})",
        "confirm-title": "Allow this action?",
        "confirm-polkit": "Vital OS will ask for an administrator through polkit. This is not a root shell.",
        "confirm-exact": "This will run:",
        "not-executed": "Not run.",
        "history-cleared": "History cleared from this computer.",
        "wipe-history": "Erase history",
        "wipe-history-body": "This deletes the assistant's local history. It does not delete the action log.",
        "key-stored": "The key is in the system keyring. It is not written to a file.",
        "key-missing": "No key stored.",
        "key-remove": "Remove key",
        "language": "Language",
        "language-system": "System",
        "language-en": "English",
        "language-he": "Hebrew",
        "hotkey": "Overlay shortcut",
        "hotkey-help": "GNOME reads this from the Vital Assistant extension. Super+Space is the default. The layout switch moves to Super+Shift+Space.",
        "actions": "System actions",
        "actions-help": "Allowlisted changes still ask you first. Privileged installs use polkit.",
        "shell-hook": "Explain failed commands",
        "shell-hook-help": "After a failed command, explain the error. A suggested command is shown and is not run.",
        "send-context": "Include the shell directory and last command when you ask from the terminal",
        "offer-files": "Offer selected files",
        "offer-window": "Offer the active window",
        "offer-clipboard": "Offer the clipboard",
        "offer-screenshot": "Offer a screenshot",
        "context-help": "Off by default. Turning one on only shows the control. Each question still starts with that control off.",
        "history": "History",
        "history-help": "Questions and answers stay on this computer. They are not sent to vital-os.org.",
        "local-device": "Local model device",
        "device-auto": "Automatic (GPU if available, otherwise CPU)",
        "device-cpu": "CPU",
        "device-gpu": "GPU",
        "api-key": "API key",
        "base-url": "Base URL",
        "model": "Model",
        "save": "Save",
        "saved": "Saved.",
        "provider-grok": "Grok (xAI)",
        "provider-openai": "OpenAI-compatible",
        "provider-ollama": "Ollama on this computer",
        "provider-local": "Local model (llama.cpp)",
        "provider-auto": "Automatic",
        "connection": "Connection",
        "permissions": "Permissions",
        "context": "Context",
        "appearance": "Appearance",
        "thinking": "Thinking…",
        "copy": "Copy",
        "copied": "Copied.",
        "no-command": "No command.",
        "dangerous-window": "This looks like {risk}. Confirm it in the terminal by typing the command or yes.",
        "screenshot-text-only": "The screenshot stays on this computer. This model reads text only, so the image itself is not sent.",
        "extension-missing": "The active window is unavailable until the Vital Assistant GNOME extension is running.",
        "files-blocked": "That file looks like a key or password file, so it was not attached.",
        "action-log": "Actions are logged under your state directory.",
        "offline-local": "On this computer",
        "remote-warning": "Personal context will leave this computer.",
    },
    "he": {
        "app-name": "עוזר ויטל",
        "overlay-placeholder": "שאלו את ויטל…",
        "overlay-hint": "Enter שולח. Esc סוגר. שום דבר במערכת לא משתנה לפני אישור.",
        "settings": "הגדרות",
        "ask": "שאלו",
        "cancel": "ביטול",
        "confirm": "אישור",
        "run": "הפעלה",
        "close": "סגירה",
        "provider": "ספק",
        "provider-answering": "עונה באמצעות {provider}",
        "disclosure-none": "לא נכלל הקשר אישי. התשובה מגיעה מ{provider}.",
        "disclosure-send": "הבקשה כוללת {items}. היעד הוא {destination}.",
        "dest-local": "המחשב הזה בלבד",
        "context-files": "קבצים",
        "context-window": "החלון הפעיל",
        "context-clipboard": "לוח הגזירים",
        "context-screenshot": "צילום מסך",
        "files-chip": "קבצים ({count})",
        "confirm-title": "לאפשר את הפעולה?",
        "confirm-polkit": "ויטל תבקש הרשאת מנהל דרך polkit. זו אינה מעטפת root.",
        "confirm-exact": "זה מה שירוץ:",
        "not-executed": "לא הופעל.",
        "history-cleared": "ההיסטוריה נמחקה מהמחשב הזה.",
        "wipe-history": "מחיקת היסטוריה",
        "wipe-history-body": "הפעולה מוחקת את היסטוריית העוזר מהמחשב. יומן הפעולות נשאר.",
        "key-stored": "המפתח נשמר במחזיק המפתחות של המערכת, לא בקובץ.",
        "key-missing": "אין מפתח שמור.",
        "key-remove": "הסרת מפתח",
        "language": "שפה",
        "language-system": "שפת המערכת",
        "language-en": "English",
        "language-he": "עברית",
        "hotkey": "קיצור לשכבת העוזר",
        "hotkey-help": "GNOME קורא את הקיצור מההרחבה. ברירת המחדל היא Super+Space. החלפת הפריסה עוברת ל-Super+Shift+Space.",
        "actions": "פעולות מערכת",
        "actions-help": "פעולות מהרשימה המותרת עדיין מבקשות אישור. התקנות שדורשות הרשאה עוברות דרך polkit.",
        "shell-hook": "הסבר לפקודות שנכשלו",
        "shell-hook-help": "אחרי פקודה שנכשלה מוצג הסבר. פקודה מוצעת מוצגת ולא מופעלת.",
        "send-context": "לכלול את התיקייה והפקודה האחרונה כששואלים מהמסוף",
        "offer-files": "להציע קבצים שנבחרו",
        "offer-window": "להציע את החלון הפעיל",
        "offer-clipboard": "להציע את לוח הגזירים",
        "offer-screenshot": "להציע צילום מסך",
        "context-help": "כבוי כברירת מחדל. ההפעלה רק מציגה את המתג. כל שאלה מתחילה כשהמתג כבוי.",
        "history": "היסטוריה",
        "history-help": "השאלות והתשובות נשארות במחשב הזה. הן לא נשלחות אל vital-os.org.",
        "local-device": "התקן למודל המקומי",
        "device-auto": "אוטומטי (GPU אם יש, אחרת CPU)",
        "device-cpu": "CPU",
        "device-gpu": "GPU",
        "api-key": "מפתח API",
        "base-url": "כתובת בסיס",
        "model": "מודל",
        "save": "שמירה",
        "saved": "נשמר.",
        "provider-grok": "Grok ‏(xAI)",
        "provider-openai": "תואם OpenAI",
        "provider-ollama": "Ollama במחשב הזה",
        "provider-local": "מודל מקומי (llama.cpp)",
        "provider-auto": "אוטומטי",
        "connection": "חיבור",
        "permissions": "הרשאות",
        "context": "הקשר",
        "appearance": "תצוגה",
        "thinking": "חושב…",
        "copy": "העתקה",
        "copied": "הועתק.",
        "no-command": "אין פקודה.",
        "dangerous-window": "זה נראה כמו {risk}. אפשר לאשר במסוף על ידי הקלדת הפקודה או yes.",
        "screenshot-text-only": "צילום המסך נשאר במחשב. המודל הזה קורא טקסט בלבד, ולכן התמונה עצמה לא נשלחת.",
        "extension-missing": "החלון הפעיל לא זמין עד שהרחבת GNOME של העוזר פועלת.",
        "files-blocked": "הקובץ נראה כמו מפתח או סיסמה, ולכן לא צורף.",
        "action-log": "הפעולות נרשמות בתיקיית המצב של המשתמש.",
        "offline-local": "במחשב הזה",
        "remote-warning": "הקשר אישי ייצא מהמחשב הזה.",
    },
}


class Catalog:
    def __init__(self, language: str) -> None:
        self.language = language if language in STRINGS else "en"
        self.rtl = self.language == "he"

    def __call__(self, key: str, **values: object) -> str:
        table = STRINGS[self.language]
        text = table.get(key) or STRINGS["en"].get(key) or key
        if values:
            return text.format(**values)
        return text


def resolve_language(preference: str) -> str:
    choice = (preference or "system").strip().lower()
    if choice in {"en", "english"}:
        return "en"
    if choice in {"he", "iw", "hebrew", "עברית"}:
        return "he"
    if choice != "system":
        return "en"
    for var in ("LC_ALL", "LC_MESSAGES", "LANG"):
        value = os.environ.get(var, "")
        lowered = value.lower()
        if lowered.startswith("he") or lowered.startswith("iw"):
            return "he"
    return "en"


def translator(preference: str) -> Catalog:
    return Catalog(resolve_language(preference))
