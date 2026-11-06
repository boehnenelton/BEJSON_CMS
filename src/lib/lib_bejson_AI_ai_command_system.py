"""
Library:        lib_bejson_AI_ai_command_system.py
Family:         AI
Description:    Atomic, UI/provider-agnostic slash-command registry and
                 dispatcher. Generalized out of NewAgent's
                 lib_bejson_newagent_commands.py -- that file's actual
                 40-command if/elif chain (/cd, /dryrun, /amnesia, ...) is
                 NewAgent-specific application logic bound to its own ctx
                 dict shape and stays there. What's extracted here is the
                 reusable mechanism underneath it: parse "/cmd args", look
                 up a registered handler, dispatch to it (sync or async,
                 transparently -- NewAgent's dispatcher had to become async
                 for one command that needed a blocking network call off
                 the event loop; this one supports both from the start so
                 that's a non-issue), auto-generate a /help listing, and
                 build a standard About block matching Section 9.2's
                 About/Info menu requirement (credit, name, description,
                 version, date) for any project's terminal/CLI menu.
Version:        1.0.0
Date:           2026-08-13
Author:         Elton Boehnen
Contact:        boehnenelton2024@gmail.com | boehnenelton2024.pages.dev | github.com/boehnenelton
Format_Creator: Elton Boehnen
RELATIONAL_ID:  22b377fc-fd6e-4187-a9e6-8199003bef4a

Changelog:
  1.0.0 (2026-08-13) -- Initial creation.
"""

import asyncio
import inspect
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger("lib_bejson_AI_ai_command_system")

VERSION = "1.0.0"


@dataclass
class Command:
    name: str                       # canonical form, e.g. "/cd"
    handler: Callable
    help_text: str = ""
    aliases: Tuple[str, ...] = field(default_factory=tuple)


class CommandRegistry:
    """
    Register handlers, then dispatch raw input strings to them.

    Handler signature: handler(arg: str, *extra_args, **extra_kwargs) -> Any
    Handlers may be sync or async -- dispatch() awaits async handlers and
    calls sync ones directly, so callers never need to know which is which
    (this is exactly the gap that forced NewAgent's whole dispatcher to
    become async for just one command; registering handlers individually
    as sync/async avoids that).

    Example:
        reg = CommandRegistry()
        reg.register("/cd", handle_cd, help_text="Change directory", aliases=["/goto"])
        reg.register("/amnesia", handle_amnesia_async, help_text="Wipe and recap session")

        processed, output = await reg.dispatch("/cd ..", ctx)
    """

    def __init__(self, *, unknown_command_message: str = "Unknown command: {cmd}. Type /help for a list."):
        self._commands: Dict[str, Command] = {}
        self._unknown_message = unknown_command_message

    def register(
        self,
        name: str,
        handler: Callable,
        *,
        help_text: str = "",
        aliases: Optional[List[str]] = None,
    ) -> None:
        name = name.lower()
        if not name.startswith("/"):
            name = "/" + name
        aliases = tuple(a.lower() if a.startswith("/") else "/" + a.lower() for a in (aliases or []))

        cmd = Command(name=name, handler=handler, help_text=help_text, aliases=aliases)
        if name in self._commands:
            logger.warning(f"[ai_command_system] Overwriting existing command registration for {name!r}.")
        self._commands[name] = cmd
        for alias in aliases:
            self._commands[alias] = cmd

    def unregister(self, name: str) -> None:
        name = name.lower()
        if not name.startswith("/"):
            name = "/" + name
        cmd = self._commands.pop(name, None)
        if cmd:
            # Also drop any aliases pointing at the same Command object.
            for key in [k for k, v in self._commands.items() if v is cmd]:
                del self._commands[key]

    async def dispatch(self, raw: str, *extra_args, **extra_kwargs) -> Tuple[bool, Optional[Any]]:
        """
        Parse raw ("/cmd rest of the line") and route to the registered
        handler. Returns (processed, output):
          processed=False  -- raw wasn't a registered command at all (not
                              even an unknown-command message; the string
                              didn't start with "/" or had no content).
                              Caller should treat raw as ordinary input.
          processed=True, output=<message or None> -- command matched (or
                              matched nothing and produced the configured
                              unknown-command message).
        """
        raw = (raw or "").strip()
        if not raw.startswith("/"):
            return False, None

        parts = raw.split(maxsplit=1)
        name = parts[0].lower()
        arg = parts[1] if len(parts) > 1 else ""

        cmd = self._commands.get(name)
        if cmd is None:
            return True, self._unknown_message.format(cmd=name)

        try:
            if inspect.iscoroutinefunction(cmd.handler):
                result = await cmd.handler(arg, *extra_args, **extra_kwargs)
            else:
                result = cmd.handler(arg, *extra_args, **extra_kwargs)
            return True, result
        except Exception as e:
            logger.error(f"[ai_command_system] Handler for {name!r} raised: {e}")
            return True, f"Error running {name}: {e}"

    def build_help_text(self, *, title: str = "Commands:", color_fn: Optional[Callable[[str], str]] = None) -> str:
        """
        Auto-generated /help listing from registered commands, one entry
        per canonical name (aliases aren't listed separately). Pass
        color_fn (e.g. lambda s: f"{ANSI_RED}{s}{ANSI_RESET}") to colorize
        each line the way NewAgent's TUI did -- this file has no ANSI/TUI
        dependency of its own, so plain text is the default.
        """
        seen = set()
        lines = [title]
        for cmd in self._commands.values():
            if cmd.name in seen:
                continue
            seen.add(cmd.name)
            label = cmd.name
            if cmd.aliases:
                label += " (" + ", ".join(cmd.aliases) + ")"
            line1 = color_fn(label) if color_fn else label
            line2 = f"- {cmd.help_text}" if cmd.help_text else "-"
            lines.append(line1)
            lines.append(line2)
        return "\n" + "\n".join(lines) + "\n"

    def list_commands(self) -> List[str]:
        """Canonical command names only (no aliases, no duplicates)."""
        seen = set()
        out = []
        for cmd in self._commands.values():
            if cmd.name not in seen:
                seen.add(cmd.name)
                out.append(cmd.name)
        return out


def ai_build_about_text(
    *,
    product_name: str,
    version: str,
    description: str = "",
    date: str = "",
    author: str = "Elton Boehnen",
    contact: str = "boehnenelton2024@gmail.com",
    website: str = "boehnenelton2024.pages.dev",
    format_creator: str = "Elton Boehnen",
    format_name: str = "BEJSON / MFDB",
) -> str:
    """
    Standard About/Info block per the family's Section 9.2 crediting
    requirement (terminal scripts and web apps: credit, name, description,
    version, date). Generalized from NewAgent's build_about_text(), which
    hardcoded all of these to itself.
    """
    lines = [f"\n{product_name}"]
    if description:
        lines.append(description)
    lines.append(f"Version:        {version}")
    if date:
        lines.append(f"Date:           {date}")
    lines.append(f"Author:         {author}")
    lines.append(f"Contact:        {contact}")
    lines.append(f"Website:        {website}")
    lines.append(f"Format Creator: {format_creator}")
    lines.append(f"Format:         {format_name}")
    return "\n".join(lines) + "\n"
