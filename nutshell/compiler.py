from contextlib import suppress

from nutshell.cli import cli


def _handle_rule(rulefile, include_header, seg):
    """
    rulefile: stream to write to
    include_header: whether to include the compiled-by header or not
    seg: @RULE-segment data as a list of lines

    Writes @RULE segment to output stream
    """
    if seg is None:
        return
    name = seg.pop(0)
    rulefile.append(f'@RULE {name}')
    if include_header:
        rulefile.append(cli.result.transpile.header)
    rulefile.extend(seg)


def _iter_transitions(tbl):
    """
    tbl: nutshell.segment_types.table.table.Table object
    yield: lines to write to Golly table

    Yields resultant transitions of tbl, inserting comments where
    necessitated (e.g. if -s and/or -c has been passed)
    """
    src, cmt = cli.result.transpile.comment_src, cli.result.transpile.preserve_comments
    seen = set()
    for tr in tbl:
        if tr.ctx not in seen:
            seen.add(tr.ctx)
            lno, start, end = tr.ctx
            start, end = None if not start else start - 1, None if end is None else end - 1
            if cmt:
                yield from [tbl.comments.pop(cmt_lno) for cmt_lno in list(tbl.comments) if cmt_lno < lno]
            if src:
                # yield ''
                yield src.format(line=lno+tbl.start, span=tbl[lno-1][start:end])
            if cmt and lno in tbl.comments:
                yield '{}{}'.format(', '.join(map(str, tr)), tbl.comments.pop(lno))
                continue
        yield ', '.join(map(str, tr))


def _handle_table(rulefile, tbl):
    """
    rulefile: stream to write to
    tbl: segment_types.table.table.Table object

    Formats all info from `tbl` as necessary to comply with Golly's
    ruletable format (e.g. var declarations and directives and all)
    """
    rulefile.append('@TABLE')
    if tbl[0] is None:  # sentinel from segmentor.py indicating not to touch
        rulefile.extend(tbl[1:])
        return
    rulefile.append(f"neighborhood: {tbl.directives.pop('neighborhood')}")
    for directive, value in tbl.directives.items():
        rulefile.append(f'{directive}: {value}')
    rulefile.append('')
    for var, states in tbl.vars.items():
        if var.rep == -1:
            continue
        # set() removes duplicates and gives braces
        # Golly gives up reading variables past a certain length so we unfortunately have to .replace(' ', '')
        rulefile.append(f'var {var.name}.0 = ' + f'{set(states)}'.replace(' ', ''))
        rulefile.extend(f'var {var.name}.{suf} = {var.name}.0' for suf in range(1, 1 + var.rep))
    rulefile.append('')
    rulefile.extend(_iter_transitions(tbl))


def compile(parsed):
    """
    parsed: dict of operated-upon segments from Nutshell file
    return: completed Golly table therefrom
    """
    rulefile = []
    with suppress(KeyError):
        _handle_rule(rulefile, '@NUTSHELL' in parsed, parsed.pop('@NUTSHELL', parsed.pop('@RULE', None)))
    with suppress(KeyError):
        _handle_table(rulefile, parsed.pop('@TABLE'))
    for label, segment in parsed.items():
        rulefile.extend(('', label, *segment))
    return '\n'.join(rulefile) + '\n'
