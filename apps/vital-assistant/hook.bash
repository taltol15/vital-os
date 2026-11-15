#!/bin/bash
# Vital Assistant shell helpers.
# ask and ?? suggest a command. vital still waits for confirmation.
# The failure hint is off unless shell_hook=1. Stderr is captured only then.
# This file never executes a model suggestion by itself.

ask() {
    command vital ask "$@"
}

alias '??'=ask

_vital_assistant_runtime() {
    local dir="${XDG_RUNTIME_DIR:-${HOME}/.cache}/vital-assistant"
    mkdir -p "$dir"
    chmod 700 "$dir" 2>/dev/null || true
    printf '%s\n' "$dir"
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

_vital_assistant_ensure_tee() {
    local errfile="$1"
    if [[ -n "${_VITAL_ASSISTANT_TEE:-}" ]]; then
        return 0
    fi
    if ! _vital_assistant_hook_on; then
        return 0
    fi
    mkdir -p "$(dirname "$errfile")"
    : >> "$errfile"
    _VITAL_ASSISTANT_TEE=1
    # shellcheck disable=SC2094
    exec 2> >(tee -a "$errfile" >&2)
}

_vital_assistant_record() {
    local status=$?
    local dir last errfile
    dir="$(_vital_assistant_runtime)"
    errfile="${dir}/last.err"
    printf '%s\n' "$status" > "${dir}/last.exit"
    last=""
    if last="$(fc -ln -1 2>/dev/null)"; then
        last="${last#"${last%%[![:space:]]*}"}"
        printf '%s\n' "$last" > "${dir}/last.cmd"
    fi
    if [[ "$status" -eq 0 ]]; then
        : > "$errfile"
        _vital_assistant_ensure_tee "$errfile"
        return 0
    fi
    if ! _vital_assistant_hook_on; then
        return 0
    fi
    VITAL_ASSISTANT_EXIT="$status" VITAL_ASSISTANT_LAST="$last" \
        command vital ask --from-hook --exit "$status" --command "$last" --stderr-file "$errfile" </dev/null
    : > "$errfile"
    _vital_assistant_ensure_tee "$errfile"
    return 0
}

case $- in
    *i*)
        if [[ -z "${PROMPT_COMMAND:-}" ]]; then
            PROMPT_COMMAND="_vital_assistant_record"
        elif [[ "${PROMPT_COMMAND}" != *_vital_assistant_record* ]]; then
            PROMPT_COMMAND="_vital_assistant_record;${PROMPT_COMMAND}"
        fi
        ;;
esac
