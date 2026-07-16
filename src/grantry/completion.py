"""Shell completion scripts for grantry.

`grantry completion <shell>` prints one of these; you source it from your shell
rc file. Completion for an identity argument calls the hidden
`grantry _complete-identities`, which reads the local identity cache, so pressing
TAB never blocks on the network.
"""

from __future__ import annotations

SHELLS = ("bash", "zsh", "fish")

# Kept in sync with the subcommands registered in cli.py.
_SUBS = (
    "login logout version instances use ls audit mcp graph run switch "
    "credential-process console populate check status init admin install uninstall completion"
)

_BASH = """\
_grantry_complete() {{
    local cur prev sub
    cur="${{COMP_WORDS[COMP_CWORD]}}"
    prev="${{COMP_WORDS[COMP_CWORD-1]}}"
    sub="${{COMP_WORDS[1]}}"
    if [ "$COMP_CWORD" -eq 1 ]; then
        COMPREPLY=( $(compgen -W "{subs}" -- "$cur") )
        return
    fi
    case "$sub" in
        run|switch|console)
            if [ "$COMP_CWORD" -eq 2 ]; then
                COMPREPLY=( $(compgen -W "$(grantry _complete-identities 2>/dev/null)" -- "$cur") )
            fi
            ;;
        credential-process)
            if [ "$prev" = "--identity" ]; then
                COMPREPLY=( $(compgen -W "$(grantry _complete-identities 2>/dev/null)" -- "$cur") )
            fi
            ;;
        completion)
            COMPREPLY=( $(compgen -W "bash zsh fish" -- "$cur") )
            ;;
    esac
}}
complete -F _grantry_complete grantry
"""

_ZSH = """\
_grantry_complete() {{
    local -a subs
    subs=({subs})
    if (( CURRENT == 2 )); then
        compadd -- $subs
        return
    fi
    case "${{words[2]}}" in
        run|switch|console)
            (( CURRENT == 3 )) && compadd -- ${{(f)"$(grantry _complete-identities 2>/dev/null)"}}
            ;;
        credential-process)
            [[ "${{words[CURRENT-1]}}" == "--identity" ]] && \\
                compadd -- ${{(f)"$(grantry _complete-identities 2>/dev/null)"}}
            ;;
        completion)
            compadd bash zsh fish
            ;;
    esac
}}
compdef _grantry_complete grantry
"""

_FISH = (
    "function __grantry_ids\n"
    "    grantry _complete-identities 2>/dev/null\n"
    "end\n"
    "complete -c grantry -f\n"
    'complete -c grantry -n __fish_use_subcommand -a "{subs}"\n'
    'complete -c grantry -n "__fish_seen_subcommand_from run switch console" -a "(__grantry_ids)"\n'
    'complete -c grantry -n "__fish_seen_subcommand_from credential-process" -l identity'
    ' -a "(__grantry_ids)"\n'
    'complete -c grantry -n "__fish_seen_subcommand_from completion" -a "bash zsh fish"\n'
)

_TEMPLATES = {"bash": _BASH, "zsh": _ZSH, "fish": _FISH}


def completion_script(shell: str) -> str:
    template = _TEMPLATES[shell]
    return template.format(subs=_SUBS)
