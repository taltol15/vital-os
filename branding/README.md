# Vital OS visual language

Vital OS uses an original identity called **Nocturne**. It is graphite and ivory, with a single refined accent: champagne gold. Emerald appears only as a success color and as an optional accent in Vital Welcome. Nothing here is the NVIDIA, Ubuntu, or GNOME logo, and the palette is not Yaru, Adwaita blue, or Pop orange.

The desktop still *uses* upstream open-source components (GNOME, Adwaita as the widget base, Papirus icons, Inter, IBM Plex). Those are tools. The mark, wordmark, wallpapers, boot splash, GRUB theme, and color tokens are original.

## Mark

The symbol is a thin gold ring, an ivory chevron, and a gold point at the apex, with a short gold baseline. It is meant to read as a pulse that has settled, and as the letter V, without becoming a wordmark by itself.

- `logo/vital-symbol.svg` — symbol only
- `logo/vital-wordmark.svg` — “VITAL OS”
- `logo/vital-lockup.svg` — symbol plus wordmark

Clear space: keep at least half the ring’s radius empty around the symbol. Do not recolor the ring to blue, green, or white-on-white. On light backgrounds, use the graphite ring variant by swapping the ivory stroke to `#141820` and keeping the gold.

Minimum size: 16 px for the symbol. Below that, use the gold ring alone.

## Color

Tokens live in `palette.json`.

| Token | Hex | Use |
| --- | --- | --- |
| Graphite 950 | `#07080B` | Boot, letterbox, deepest background |
| Graphite 900 | `#0E1116` | Desktop field, window background |
| Graphite 800 | `#161A21` | Top bar, header bars |
| Graphite 700 | `#1E242E` | Cards, menus |
| Graphite 600 | `#2C3442` | Hairlines, hover |
| Ivory 50 | `#F6F1E7` | Primary text |
| Ivory 300 | `#C9C2B4` | Secondary text |
| Champagne 500 | `#C6A56A` | Accent, focus, selection |
| Champagne 300 | `#E4C992` | Highlight text on graphite |
| Emerald 500 | `#3E9B7A` | Success, optional accent |
| Danger 500 | `#C45C4A` | Destructive actions only |

Dark mode is the default. Light mode, chosen in Vital Welcome, swaps surfaces to ivory and text to graphite. The boot splash, GRUB menu, and GNOME Shell chrome stay dark so the machine has one face from firmware to the clock.

## Type

- Interface and wordmark: **Inter** (SIL Open Font License), package `fonts-inter`.
- Monospace: **IBM Plex Mono** (SIL Open Font License), package `fonts-ibm-plex`.
- Broad script coverage: **Noto Sans**, package `fonts-noto-core`.

UI size is 11 pt. The wordmark is Inter Medium, tracked open. We do not vendor font binaries; the image build installs the Ubuntu archive packages, which ship the OFL license texts.

## Icons

Papirus Dark (`papirus-icon-theme`, GPL-3.0) is the icon theme. During the image build, `papirus-folders` 1.14.0 (MIT, Papirus Development Team) retints folder icons to **palebrown**, the closest Papirus folder color to champagne. The cursor stays Adwaita.

## Wallpapers

- `wallpapers/nocturne.svg` — default. Graphite field, gold halo, the Vital mark.
- `wallpapers/nocturne-arc.svg` — quieter alternate, one arc and a small ring.

Both are original geometry. The image build rasterizes them to PNG because GNOME and GRUB want bitmaps. Do not trace third-party photography into this directory.

## Where the theme is applied

| Surface | Implementation |
| --- | --- |
| GTK 3 and libadwaita apps | User `gtk.css` color overrides on Adwaita / Adwaita-dark. Libadwaita ignores classic GTK themes, so Vital OS tunes named colors instead of shipping a second widget theme. |
| GNOME Shell and overview | `/usr/share/themes/Vital/gnome-shell/`, selected with the User Themes extension |
| Dock | Dash to Dock, bottom, fixed, graphite, gold running dots |
| Login | GDM dconf: Nocturne wallpaper, Vital logo, banner text |
| Boot | Plymouth script theme `vitalos` |
| Firmware menu | GRUB theme `vital` |
| About | `/etc/os-release` `NAME=Vital OS`, `LOGO=vitalos` |

Accent presets in Vital Welcome rewrite the per-user GTK colors (champagne, emerald, ivory). The shell chrome stays champagne.
