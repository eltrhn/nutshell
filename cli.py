from ergo import CLI, Group


DEFAULT_HEADER = '''\
*********************************
**** COMPILED FROM RUELTABEL ****
*********************************\
'''


cli = CLI()
cli.grp_0 = Group(XOR='find|preview|normal')
preview = cli.command('preview', XOR='find|preview|normal', OR='preview|normal')


@cli.grp_0.clump(AND='infile|outdir')
@cli.arg()
def infile(path):
    """rueltabel-formatted input file"""
    return path


@cli.clump(OR='preview|normal')
@cli.grp_0.clump(AND='infile|outdir')
@cli.grp_0.arg()
def outdir(path):
    """Directory to create output file in"""
    return path


@cli.grp_0.flag(short='t', default=DEFAULT_HEADER)
def header(text=''):
    """Change or hide 'COMPILED FROM RUELTABEL' header"""
    return text or DEFAULT_HEADER


@cli.grp_0.flag(short='s', default=False)
def comment_src():
    """Comment each tabel source line above the final table line(s) it transpiles to"""
    return True


@cli.clump(XOR='find|preview|normal')
@cli.flag(short='f', default=None)
def find(transition):
    """Locate first transition in `infile` that matches"""
    return tuple(s if s == '*' else int(s) for s in map(str.strip, transition.split(',')))


@cli.clump(XOR='verbose|quiet')
@cli.flag('verbosity', namespace={'count': 0}, default=0)
def verbose(nsp):
    """Repeat for more verbosity; max x4"""
    if nsp.count < 4:
        nsp.count += 1
    return nsp.count


@cli.clump(XOR='verbose|quiet')
@cli.flag(default=False)
def quiet():
    return True


@preview.arg(required=True)
def transition(tr):
    """rueltabel-formatted transition to preview"""
    return tr


@preview.flag(short='n', default='Moore')
def neighborhood(value):
    """Neighborhood to consider transition part of"""
    if value.replace(' ', '') not in ('Moore', 'vonNeumann', 'hexagonal'):
        raise ValueError("Invalid preview-transition neighborhood (must be one of 'Moore', 'vonNeumann', 'hexagonal')")
    return value


@preview.flag(short='o', default='?')
def states(num):
    """Number of states to include in transition (default: guess)"""
    if not num.isdigit() and num != '?':
        raise ValueError('Preview n_states must be ? or an integer')
    return str(num)


ARGS = cli.parse(strict=True)
