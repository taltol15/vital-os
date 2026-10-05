# Vital Assistant shortcuts for zsh. The failure hint is off unless shell_hook=1.

ask() {
    command vital ask "$@"
}

'??'() {
    command vital ask "$@"
}

_vital_assistant_hook_on() {
    local file
    for file in "${HOME}/.config/vitalos/assistant.conf" /etc/vital/assistant.conf; do
        if [[ -f "$file" ]] && grep -q '^shell_hook=1$' "$file"; then
            return 0
        fi
    done
    return 1
}

_vital_assistant_precmd() {
    local status=$?
    if (( status == 0 )); then
        return 0
    fi
    if ! _vital_assistant_hook_on; then
        return 0
    fi
    local last="${history[$HISTCMD]}"
    VITAL_ASSISTANT_EXIT="$status" VITAL_ASSISTANT_LAST="$last" \
        command vital ask --from-hook --exit "$status" --command "$last" </dev/null
}

autoload -Uz add-zsh-hook
add-zsh-hook precmd _vital_assistant_precmd
