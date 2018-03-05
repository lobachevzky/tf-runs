import os
from contextlib import contextmanager
from pathlib import Path

import subprocess

import shutil
from pprint import pprint

import yaml
from nose.tools import assert_in, eq_, ok_

from runs import main
from runs.db import DBPath
from runs.run import Run
from runs.util import NAME

CHILDREN = 'children'


def sessions():
    try:
        output = subprocess.check_output('tmux list-session -F "#{session_name}"'.split(),
                                         universal_newlines=True)
        assert isinstance(output, str)
        return output.split('\n')
    except subprocess.CalledProcessError:
        return []


def get_name(nodes, name):
    return next(n for n in nodes if n[NAME] == name)


class Tests:
    def __init__(self):
        self.command = """\
import argparse

parser = argparse.ArgumentParser()
parser.add_argument('--option', default=0)
print(vars(parser.parse_args()))\
"""
        self.work_dir = '/tmp/test-run-manager'
        self.root = '.runs'
        self.description = 'test new command'
        self.name = 'test_run'
        self.sep = DBPath('').sep

    @property
    def db(self):
        with Path(self.work_dir, 'runs.yml').open() as f:
            return yaml.load(f)

    def db_entry(self, path):
        if not path:
            return self.db
        *path, name = path.split(self.sep)
        entry = self.db_entry(self.sep.join(path))
        assert_in(CHILDREN, entry)
        return get_name(entry[CHILDREN], name)

    @contextmanager
    def _setup(self, path, dir_names, flags):
        assert isinstance(path, str)
        assert isinstance(dir_names, list)
        assert isinstance(flags, list)
        Path(self.work_dir).mkdir(exist_ok=True)
        os.chdir(self.work_dir)
        if any([dir_names, flags]):
            with Path(self.work_dir, '.runsrc').open('w') as f:
                f.write(
                    """\
    [filesystem]
    root = {}
    db_path = runs.yml
    dir_names = {}

    [flags]
    {}\
    """.format(self.root, ' '.join(dir_names), '\n'.join(flags)))
        subprocess.run(['git', 'init', '-q'], cwd=self.work_dir)
        with Path(self.work_dir, '.gitignore').open('w') as f:
            f.write('.runsrc\nruns.yml')
        subprocess.run(['git', 'add', '.gitignore'], cwd=self.work_dir)
        subprocess.run(['git', 'commit', '-qam', 'init'], cwd=self.work_dir)
        main.main(['new', path, self.command, "--description=" + self.description, '-q'])
        yield
        subprocess.run('tmux kill-session -t'.split() + [path])
        shutil.rmtree(self.work_dir)

    def check_new(self, path, dir_names, flags):
        name = path.split(self.sep)[-1]

        # test tmux
        assert_in('"' + path + '"', sessions())

        entry = self.db_entry(path)

        # check values that should probably be mocks
        for key in ['commit', 'datetime']:
            assert_in(key, entry)

        # check known values
        attrs = dict(description=self.description,
                     input_command=self.command,
                     name=name)
        for key, attr in attrs.items():
            assert_in(key, entry)
            eq_(entry[key], attr)
        for flag in flags:
            assert_in(flag, entry['full_command'])

        # check file structure
        for dir_name in dir_names:
            path = Path(self.work_dir, self.root, dir_name, path)
            ok_(path.exists(), msg="{} does not exist.".format(path))

    def test_new(self):
        for path in ['test_run', 'subdir/test_run']:
            for dir_names in [[], ['checkpoints', 'tensorboard']]:
                for flags in [[], ['--option=1']]:
                    with self._setup(path, dir_names, flags):
                        yield self.check_new, path, dir_names, flags

    # def test_remove(self):