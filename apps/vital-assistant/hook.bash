#!/bin/bash
# Vital Assistant shell helpers. The failure hint is off unless shell_hook=1.
# Shortcuts are ask and ??. Confirmed commands still go through vital ask.

ask() {
    command vital ask "$@"
}

alias '??'=ask

_vital_assistant_hook_on() {
    local file
    for file in "${HOME}/.config/vitalos/assistant.conf" /etc/vital/assistant.conf; do
        if [ -f "$file" ] && grep -q '^shell_hook=1$' "$file"; then
            return 0
        fi
    done
    return 1
}

_vital_assistant_after_command() {
    local status=$?
    if [ "$status" -eq 0 ]; then
        return 0
    fi
    if ! _vital_assistant_hook_on; then
        return 0
    fi
    local last
    last=$(history 1 | sed 's/^ *[0-9][0-9]* *//')
    VITAL_ASSISTANT_EXIT="$status" VITAL_ASSISTANT_LAST="$last" \
        command vital ask --from-hook --exit "$status" --command "$last" </dev/null
    return 0
}

case $- in
    *i*)
        if [ -z "${PROMPT_COMMAND:-}" ]; then
            PROMPT_COMMAND="_vital_assistant_after_command"
        elif ! printf '%s' "$PROMPT_COMMAND" | grep -q _vital_assistant_after_command; then
            PROMPT_COMMAND="_vital_assistant_after_command;${PROMPT_COMMAND}"
        fi
        ;;
esac
