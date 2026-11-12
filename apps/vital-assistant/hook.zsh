# Vital Assistant shortcuts for zsh. The failure hint is off unless shell_hook=1.
# A suggested command is never run from this file.

if [[ -n "${_VITAL_ASSISTANT_ZSH:-}" ]]; then
    return 0
fi
_VITAL_ASSISTANT_ZSH=1

ask() {
    command vital ask "$@"
}

'??'() {
    command vital ask "$@"
}

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
    exec 2> >(tee -a "$errfile" >&2)
}

_vital_assistant_precmd() {
    local status=$?
    local dir last errfile
    dir="$(_vital_assistant_runtime)"
    errfile="${dir}/last.err"
    printf '%s\n' "$status" > "${dir}/last.exit"
    last="$(fc -ln -1 2>/dev/null || true)"
    last="${last#"${last%%[![:space:]]*}"}"
    if [[ -n "$last" ]]; then
        printf '%s\n' "$last" > "${dir}/last.cmd"
    fi
    if (( status == 0 )); then
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

autoload -Uz add-zsh-hook
add-zsh-hook precmd _vital_assistant_precmd
