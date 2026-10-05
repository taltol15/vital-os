# Vital OS visual language

Vital OS uses an original identity called **Nocturne**. It is graphite and ivory, with a single refined accent: champagne gold. Emerald appears only as a success color and as an optional accent in Vital Welcome. Nothing here is the NVIDIA, Ubuntu, or GNOME logo, and the palette is not Yaru, Adwaita blue, or Pop orange.

The desktop still *uses* upstream open-source components (GNOME, Adwaita as the widget base, Papirus icons, Inter, IBM Plex). Those are tools. The mark, wordmark, wallpapers, boot splash, GRUB theme, and color tokens are original.

## Mark

The symbol is a thin gold ring, a quieter inner ring, and an ivory V. The point of the V is at the bottom and the arms open upward. A small gold dot sits on that point. There is no bar under the V.

The wordmark is drawn as paths, not live type, so the spacing does not depend on which Inter file a renderer finds. VITAL is ivory. OS is smaller, champagne, and sits on the same baseline. Sidebearings are wider around the I and after the T’s crossbar.

- `logo/vital-symbol.svg` — symbol, ivory and champagne
- `logo/vital-symbol-mono.svg` — symbol in ivory only
- `logo/vital-symbol-accent.svg` — symbol in champagne only
- `logo/vital-wordmark.svg` — VITAL OS
- `logo/vital-wordmark-mono.svg` — wordmark in ivory only
- `logo/vital-lockup.svg` — symbol plus wordmark
- `logo/vital-market.svg` — Marketplace icon

Clear space: keep at least half the ring’s radius empty around the symbol. Do not recolor the ring to blue, green, or white-on-white. On light backgrounds, use the day wallpaper, which draws the chevron in graphite and the ring in champagne-700.

Minimum size: 16 px for the symbol. Below that, use the gold ring alone.

## Color

Tokens live in `palette.json`. The field is deeper than a neutral gray: graphite-1000 is the boot and letterbox color, and each step up is only a few points lighter so panels sit in the same night. Champagne stays a single accent. Do not introduce a second brand hue.

| Token | Hex | Use |
| --- | --- | --- |
| Graphite 1000 | `#050608` | Boot, letterbox, deepest background |
| Graphite 950 | `#08090C` | View background |
| Graphite 900 | `#0C0F14` | Desktop field, window background |
| Graphite 850 | `#12161C` | Day-mode text |
| Graphite 800 | `#171C24` | Top bar, header bars |
| Graphite 700 | `#1C232E` | Cards, menus |
| Graphite 600 | `#2A3140` | Hairlines, hover |
| Ivory 50 | `#F3EEE4` | Primary text |
| Ivory 100 | `#E7E0D2` | Day surfaces |
| Ivory 300 | `#C4BBAE` | Secondary text |
| Champagne 200 | `#E6D3A4` | Highlight text on graphite |
| Champagne 500 | `#C6A56A` | Accent, focus, selection |
| Champagne 700 | `#8A7040` | Pressed accent, day-mode gold |
| Emerald 500 | `#3C9A78` | Success, optional accent |
| Danger 500 | `#C45C4A` | Destructive actions only |

Dark mode is the default. Light mode, chosen in Vital Welcome, swaps surfaces to ivory and text to graphite. The boot splash, GRUB menu, and GNOME Shell chrome stay dark so the machine has one face from firmware to the clock.

## Type

- Interface and wordmark: **Inter** (SIL Open Font License), package `fonts-inter`.
- Monospace: **IBM Plex Mono** (SIL Open Font License), package `fonts-ibm-plex`.
- Broad script coverage: **Noto Sans**, package `fonts-noto-core`.

UI size is 11 pt. The wordmark is original geometry in the same spirit as a wide grotesque; the interface itself is Inter. We do not vendor font binaries; the image build installs the Ubuntu archive packages, which ship the OFL license texts.

## Icons

Papirus Dark (`papirus-icon-theme`, GPL-3.0) is the icon theme. During the image build, `papirus-folders` 1.14.0 (MIT, Papirus Development Team) retints folder icons to **palebrown**, the closest Papirus folder color to champagne. The cursor stays Adwaita.

## Wallpapers

- `wallpapers/nocturne.svg` — default dark. Graphite field, gold halo, the Vital mark.
- `wallpapers/nocturne-arc.svg` — quieter dark alternate, one arc and a small ring.
- `wallpapers/nocturne-day.svg` — light. Ivory field, graphite mark, champagne-700 ring. Vital Welcome selects this when the account is in light mode.

All three are original geometry. The image build rasterizes them to PNG because GNOME and GRUB want bitmaps. Do not trace third-party photography into this directory.

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
