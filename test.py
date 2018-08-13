#!/usr/bin/env python3.6
"""With the pytest-cov plugin installed, run this using `py.test test.py --cov=nutshell/ --cov-report html`"""
import os
import sys

import pytest

__name__, _oldname_ = 'not main!', __name__
from nutshell.main import transpile, write_rule
from nutshell.common.utils import RAND_SEED, random as nutshell_rand

ARGV = sys.argv + [None, None][len(sys.argv):]

def test_codecov():
    for fname in list(os.walk('./examples/nutshells'))[0][2]:
        with open('./examples/nutshells/' + fname) as fp:
            transpile(fp)


if _oldname_ == '__main__':
    main = ARGV[1]
    if main is None:
        pytest.main('test.py --cov=nutshell/ --cov-report=html'.split())
    elif main in ('run', 'test'):
        walk = list(os.walk('./examples/nutshells'))[0][2]
        if main == 'run':
            for fname in walk:
                if len(ARGV) < 3 or fname.split('.')[0] in ARGV[2:]:
                    write_rule(infiles=['./examples/nutshells/' + fname], outdirs=['./examples/compiled_ruletables/'])
                nutshell_rand.seed(RAND_SEED)
        else:
            for fname in walk:
                if len(ARGV) < 3 or fname.split('.')[0] in ARGV[2:]:
                    with open('./examples/nutshells/' + fname) as fp:
                        transpile(fp)
                nutshell_rand.seed(RAND_SEED)
