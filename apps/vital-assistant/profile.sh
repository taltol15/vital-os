#!/bin/bash
# Installed as /etc/profile.d/vital-assistant.sh and sourced from bashrc.
if [ -n "${BASH_VERSION:-}" ] && [ -f /usr/share/vitalos/assistant/hook.bash ]; then
    # shellcheck disable=SC1091
    . /usr/share/vitalos/assistant/hook.bash
elif [ -n "${ZSH_VERSION:-}" ] && [ -f /usr/share/vitalos/assistant/hook.zsh ]; then
    # shellcheck disable=SC1091
    . /usr/share/vitalos/assistant/hook.zsh
fi
