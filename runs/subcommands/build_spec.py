# stdlib

# first party
import re
from collections import defaultdict
from pprint import pprint
from typing import List, Set

from runs.command import Command
from runs.database import DataBase, add_query_flags
from runs.logger import Logger
from runs.run_entry import RunEntry
from runs.subcommands.new_from_spec import SpecObj


def add_subparser(subparsers):
    parser = subparsers.add_parser(
        'build-spec',
        help='Print json spec that reproduces crossproduct '
        'of flags in given patterns.')
    parser.add_argument(
        '--exclude', nargs='*', default=set(), help='Keys of flags to exclude.')
    add_query_flags(parser, with_sort=False)
    return parser


@DataBase.open
@DataBase.query
def cli(runs: List[RunEntry], logger: Logger, exclude: List[str], *args, **kwargs):
    exclude = set(exclude)
    commands = [Command.from_run(run) for run in runs]
    for command in commands:
        for group in command.arg_groups[1:]:
            if isinstance(group, list):
                logger.exit(f"Command {command} contains multiple positional argument "
                            f"groups. Currently reproduce-to-spec only supports one "
                            f"positional argument group")
    stems = {' '.join(command.stem) for command in commands}
    if not len(stems) == 1:
        logger.exit(
            "Commands do not start with the same positional arguments:",
            *commands,
            sep='\n')
    pprint(get_spec_obj(commands, exclude).dict())


def get_spec_obj(commands: List[Command], exclude: Set[str]):
    stem = ' '.join(commands[0].stem)

    def nonpositionals():
        for command in commands:
            try:
                yield from command.arg_groups[1]
            except IndexError:
                pass

    flags = defaultdict(set)
    bare_command = any(len(command.arg_groups) == 1 for command in commands)
    for nonpositional in nonpositionals():
        try:
            key, value = re.match('(-{1,2}[^=]*)="?([^"]*)"?', nonpositional).groups()
            key = key.lstrip('--')
            try:
                value = float(value)
                if value % 1 == 0:
                    value = int(value)
            except ValueError:
                pass
            if key not in exclude:
                flags[key].add(value)
        except AttributeError:
            value, = re.match('(-{1,2}.*)', nonpositional).groups()
            value = value.lstrip('--')
            if value not in exclude:
                flags[''].add(value)
                for command in commands:
                    if bare_command or nonpositional not in command.arg_groups[1]:
                        flags[''].add('')

    flags = {k: v.pop() if len(v) == 1 else list(v) for k, v in flags.items()}
    return SpecObj(command=stem, flags=flags)
