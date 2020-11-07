from collections import namedtuple
from functools import wraps
from inspect import signature
from importlib import import_module
from itertools import chain, repeat
from operator import attrgetter

import bidict
from .lark_assets.parser import Transformer, Tree, Discard, v_args

from nutshell.common.utils import KILL_WS
from nutshell.common.errors import *
from ._classes import *
from . import _symutils as symutils, _neighborhoods as nbhoods, inline_rulestring

SPECIALS = {'...', '_', 'N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW'}
Meta = namedtuple('Meta', ['lno', 'start', 'end'])


def fix(meta):
    if isinstance(meta, tuple):
        return meta
    return Meta(meta.line, meta.column, meta.end_column)


def inline(func):
    @wraps(func)
    def wrapper(self, children, meta):
        return func(self, fix(meta), *children)
    wrapper.inline = func
    return wrapper


def _add_mod(modulus, index, add, start=1):
    index += add - start
    return index % modulus + start


class MetaTuple(tuple):  # eh
    def __new__(cls, meta, it):
        return super().__new__(cls, it)
    
    def __init__(self, meta, _):
        self.meta = meta


@v_args(meta=True)
class Preprocess(Transformer):
    """
    Collect var declarations and directives
    """
    def __init__(self, tbl):
        self._tbl = tbl
        self.directives = tbl.directives
        self.vars = tbl.vars
        self.consts = {}
        self._nbhd_assigned = False
    
    def kill_string(self, val, meta, li=False, var_and_special=True):
        if isinstance(val, str):
            if val in SPECIALS and var_and_special:
                return str(val)
            if val.isdigit():
                return [int(val)] if li else int(val)
            if val in self.vars and var_and_special:
                return self.vars[val]
            if val in self.consts:
                return self.consts[val]
            raise UndefinedErr(
              fix(meta),
              f'Undefined variable {val}'
              )
        return val
    
    def kill_strings(self, val, meta):
        return [self.kill_string(i, meta) for i in val]
    
    def special_transform(self, initial, resultant, napkin):
        """
        Handle the special ~ syntax for current symmetries
        """
        special_params = {
          'length': self._tbl.trlen,
          'initial': initial,
          'resultant': resultant,
          'values': napkin,
          }.items()
        params = signature(self._tbl.symmetries.special).parameters
        return self._tbl.symmetries.special(**{k: v for k, v in special_params if k in params})
    
    def unravel_permute(self, tree, meta):
        if isinstance(tree, tuple):
            return tree
        if tree.location is None:
            return tree.value, None
        
        # We can now assume first is a tree, I think
        # ^ Update 2 years later: what is that supposed to mean

        #if cdir or range:
        raise SyntaxErr(
          fix(tree.loc.ctx),
          f"Cannot specify compass directions under {self.directives['symmetries']} symmetries"
          )
        # Nothing left to return here... right? Because permute_shorthand trees
        # will already have been transformed (by self.permute_shorthand) and
        # returned by the first conditional in this method
    
    #-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#
    
    def table(self, transitions, meta):
        return list(chain.from_iterable(transitions))
    
    @inline
    def transition(self, meta, main, aux_first=None, aux_second=None):
        if aux_first is not None and aux_first.meta == 'normal':
            # then aux_second must be 'hoisted', so apply it first
            return list(chain(main.apply_aux(aux_second), main.expand(), main.apply_aux(aux_first)))
        return list(chain(main.apply_aux(aux_first), main.expand(), main.apply_aux(aux_second)))
    
    @inline
    def print_val(self, meta, val):
        print(f"'{self._tbl[meta[0]-1].lstrip('!')}' => {self.kill_string(val, meta)}")
        raise Discard
    
    @inline
    def comment(self, meta, text):
        self._tbl.comments[meta[0]] = str(text)
        raise Discard
    
    @inline
    def end_bs(self, meta, text):
        if text.lstrip().startswith('#'):
            self._tbl.comments[meta[0]] = str(text)
        raise Discard
    
    @inline
    def directive(self, meta, name, val):
        if not isinstance(val, str):
            val = str(val)
        cmt_val = val
        if '#' in val:  # since comments are not handled otherwise
            val = val[:val.index('#')].rstrip()
        if name == 'macros':
            try:
                self._tbl.add_macros(val.translate(KILL_WS))
            except (Exception, SyntaxError) as e:
                raise Error(meta, f'Error in Python macro file: {e}')
            raise Discard
        if name in self._tbl.available_macros:
            self._tbl.set_macro(meta, name, val)
            raise Discard
        val = val.translate(KILL_WS)
        self.directives[str(name)] = val
        if name in ('n_states', 'states'):
            self._tbl.update_special_vars(val)
        elif name == 'neighborhood':
            if self._nbhd_assigned:
                raise Error(meta, '`neighborhood` directive cannot be reassigned')
            try:
                self._tbl.neighborhood = val
            except ValueError as e:
                raise Error(meta, str(e))
            self._nbhd_assigned = True
        else:
            # directives are more like comments than they are source
            self._tbl.comments[meta[0]] = f'#### {name}: {cmt_val}'
        if name == 'symmetries':
            try:
                self._tbl.add_sym_type(val)
            except ImportError as e:
                raise Error(meta, str(e))
            except (Exception, SyntaxError) as e:
                raise Error(meta, f'Error in Python symmetry file: {e}')
        raise Discard
    
    @inline
    def var_decl(self, meta, name, var):
        self.vars[VarName(name)] = self.noref_var(var, meta)
        raise Discard
    
    @inline
    def const_decl(self, meta, name, val):
        self.consts[name] = self.kill_string(val, meta)
        raise Discard
    
    def inline_binding_error(self, children, meta):
        raise SyntaxErr(
          fix(meta),
          f"Cannot use inline-binding shorthand on only one term (without spreading it over multiple terms)"
          )
    
    def permute_shorthand(self, children, meta):
        state, *permute = children
        if permute and not hasattr(self._tbl.symmetries, 'special'):
            raise SyntaxErr(
              fix(meta),
              f"Cannot use tilde-based shorthand under {self.directives['symmetries']} symmetries.\n  "
              '(Try a range of compass directions instead)'
              )
        return MetaTuple(meta, (self.kill_string(state, meta), str(permute[0]) if permute else None))
    
    @inline
    def tr_state_prefixed(self, meta, location, value):
        return TransitionState(
          self.kill_string(value, meta),
          location,
          context=meta
          )

    @inline
    def tr_state_heavpoot(self, meta, value, location):
        return self.tr_state_prefixed.inline(self, meta, location, value)

    @inline
    def tr_state_bare(self, meta, value):
        return self.tr_state_prefixed.inline(self, meta, None, value)
    
    @inline
    def cdir(self, meta, direction):
        return TransitionCDir(
          value=self._tbl.check_cdir(direction, meta),
          original=direction,
          context=meta
          )
    
    def crange(self, children, meta):
        start, end = children
        val = range(
          self._tbl.check_cdir(start, (meta.line, meta.column, len(start) + meta.column)),
          1 + self._tbl.check_cdir(end, (meta.line, meta.end_column - len(end), meta.end_column))
          )
        return TransitionCRange(
          self._tbl,
          value=val,
          original=(start, end),
          context=fix(meta)
          )

    def main(self, children, meta):
        if not self._tbl.default_sym_used and self.directives['symmetries'] == 'none':
            self._tbl.default_sym_used = True
            self._tbl.add_sym_type('none')
        
        initial, resultant = children.pop(0), children.pop(-1)
        try:
            initial = self.kill_string(initial, meta)
        except UndefinedErr as e:
            raise UndefinedErr((meta.line, meta.column, meta.column + len(str(initial))), e.msg)
        try:
            resultant = self.kill_string(resultant, meta)
        except UndefinedErr as e:
            raise UndefinedErr((meta.line, meta.end_column - len(str(resultant)), meta.end_column), e.msg)
        if hasattr(self._tbl.symmetries, 'special'):
            seq = [self.unravel_permute(i, meta) for i in children]
            try:
                napkin = dict(enumerate(self.special_transform(initial, resultant, seq), 1))
            except Exception as e:
                raise Error(
                  fix(meta),
                  f"Tilde notation raised "
                  f"{type(e).__name__}: {e}"
                  )
        else:
            idx = pure_idx = 1
            napkin = {}
            add_mod = partial(_add_mod, self._tbl.trlen)
            offset_initial = False  # whether it starts on a compass dir other than the first
            all_cdir = True  # whether all terms are tagged with a compass-direction prefix
            
            for tr_state in children:
                loc = tr_state.location
                
                if loc is None:
                    all_cdir = False
                    napkin[idx] = tr_state.value
                    idx = add_mod(idx, 1)
                    pure_idx += 1
                elif loc.is_range:
                    crange = loc.value
                    a, b = loc.orig

                    if len(crange) == 1 or not crange and not offset_initial:
                        if idx != 1:
                            raise SyntaxErr(
                              loc.ctx,
                              f'Invalid compass-direction range ({b} does not follow {a} going clockwise)'
                              )
                        offset_initial = 1
                    
                    if not crange and offset_initial:
                        crange = loc.offset_range
                    
                    if idx != crange[0]:
                        if idx == 1:
                            idx = offset_initial = crange[0]
                        else:
                            nbhd = self._tbl.neighborhood.inv
                            raise SyntaxErr(
                              (loc.ctx.lno, loc.ctx.start, len(a) + loc.ctx.start),
                              'Out-of-sequence compass direction '
                              f'(expected {nbhd[idx]}, got {nbhd[crange[0]]})'
                              )
                    
                    if isinstance(tr_state.value, InlineBinding):
                        tr_state.value.set(idx)
                        napkin[crange[0]] = tr_state.value.give()
                        crange = range(1+crange[0], 1+crange[-1])
                        idx = add_mod(idx, 1)
                        pure_idx += 1
                        tr_state.value = tr_state.value.give()
                    
                    for i in crange:
                        if i in napkin:
                            raise Error(
                              loc.ctx,
                              'Compass-direction range contains duplicate '
                              '(i.e. contains at least one compass direction used elsewhere in this transition)'
                              )
                        napkin[i] = tr_state.value
                        idx = add_mod(idx, 1)
                        pure_idx += 1
                else:
                    cdir = loc.value
                    if cdir in napkin:
                        raise SyntaxErr(
                          loc.ctx,
                          f'Duplicate compass direction {loc.orig}'
                          )
                    napkin[cdir] = tr_state.value
                    if cdir != idx:
                        if idx == 1 and not offset_initial:
                            offset_initial = cdir
                        elif cdir < idx and (not offset_initial or
                        offset_initial and pure_idx > self._tbl.trlen):
                            raise SyntaxErr(
                              loc.ctx,
                              'Out-of-sequence compass direction '
                              f'(expected {self._tbl.neighborhood.inv[idx] + (" or further" if all_cdir else "")}, got {loc.orig})'
                              )
                        pure_idx += abs(cdir - idx)
                        idx = cdir
                    idx = add_mod(idx, 1)
                    pure_idx += 1
            if all_cdir:
                napkin.update(dict.fromkeys(
                  [idx for idx in self._tbl.neighborhood.inv if idx not in napkin],
                  self.vars['any']
                  ))
            if len(napkin) != self._tbl.trlen:
                raise Error(
                  (meta.line, children[0].ctx.start, children[-1].ctx.start),
                  f"Bad transition length for {self.directives['neighborhood']} neighborhood "
                  f'(expected {2+self._tbl.trlen} terms, got {2+len(napkin)})'
                  )
        return TransitionGroup(self._tbl, initial, napkin, resultant, context=fix(meta))
    
    def hoist_aux(self, children, meta):
        for idx, i in enumerate(children):
            if isinstance(i, tuple):
                for child in i:
                    child.hoist = True
                children[idx:1+idx] = i
            else:
                i.hoist = True
        return MetaTuple('hoist', children)
    
    def normal_aux(self, children, meta):
        for idx, i in enumerate(children):
            if isinstance(i, tuple):
                children[idx:1+idx] = i
        return MetaTuple('normal', children)
    
    def cdir_delay(self, children, meta):
        return {
          'cdir': self._tbl.check_cdir(children[0], fix(meta), return_int=False),
          'delay': int(children[1]) if len(children) > 1 else None,
          'meta': fix(meta)
          }
    
    @inline
    def symmetried_aux(self, meta, symmetries, *auxiliaries):
        self._tbl.add_sym_type(symmetries)
        symmetries = symutils.get_sym_type(symmetries)
        for aux in auxiliaries:
            aux.symmetries = symmetries
        return auxiliaries
    
    @inline
    def stationary_symmetried_aux(self, meta, symmetries, *auxiliaries):
        self._tbl.add_sym_type(symmetries)
        symmetries = symutils.get_sym_type(symmetries)
        for aux in auxiliaries:
            aux.symmetries = symmetries
            aux.stationary = True
        return auxiliaries
    
    @inline
    def aux_bare(self, meta, cdir_info, val):
        cdir_to, delay = cdir_info['cdir'], cdir_info['delay']
        return Auxiliary(self._tbl, cdir_to, delay, self.kill_string(val, meta), context=meta)
    
    @inline
    def aux_bind_self(self, meta, cdir_info, cdir_from):
        cdir_from = self._tbl.check_cdir(cdir_from, fix(meta), return_int=False, enforce_int=True)
        cdir_to, delay = cdir_info['cdir'], cdir_info['delay']
        return Auxiliary(self._tbl, cdir_to, delay, Binding(cdir_from, context=(meta[0], meta[1]+len(cdir_to), meta[2])), context=meta)
    
    @inline
    def aux_map_self(self, meta, cdir_info, val):
        cdir_to, delay = cdir_info['cdir'], cdir_info['delay']
        return Auxiliary(self._tbl, cdir_to, delay, Mapping(cdir_to, self.kill_string(val, meta), context=(meta[0], meta[1]+len(cdir_to), meta[2])), context=meta)
    
    @inline
    def aux_map_other(self, meta, cdir_info, cdir_from, val):
        cdir_to, delay = cdir_info['cdir'], cdir_info['delay']
        cdir_from = self._tbl.check_cdir(cdir_from, (meta[0], meta[1] + cdir_info['meta'][1] + 1, len(cdir_from)), return_int=False, enforce_int=True)
        return Auxiliary(self._tbl, cdir_to, delay, Mapping(cdir_from, self.kill_string(val, meta), context=(meta[0], meta[1]+len(cdir_to), meta[2])), context=meta)
    
    @inline
    def range(self, meta, start, stop):
        return StateList(range(int(start), 1+int(stop)))
    
    @inline
    def range_step(self, meta, step, start, stop):
        return StateList(range(int(start), 1+int(stop), int(step)))
    
    @inline
    def noref_repeat_int(self, meta, num, multiplier):
        return self.noref_var([num], meta) * int(multiplier)
    
    @inline
    def noref_int_to_var_length(self, meta, num, var):
        return self.noref_var([num], meta) * len(self.kill_string(var, meta))
    
    @inline
    def noref_repeat_var(self, meta, var, num):
        return self.kill_string(var, meta) * int(num)
    
    @inline
    def noref_subt(self, meta, minuend, subtrhnd):
        return StateList(i for i in self.kill_string(minuend, meta) if i not in self.kill_string(subtrhnd, meta, li=True))
    
    @inline
    def noref_live_except(self, meta, subtrhnd):
        return self.noref_subt(('live', subtrhnd), meta)
    
    @inline
    def noref_all_except(self, meta, subtrhnd):
        return self.noref_subt(('any', subtrhnd), meta)
    
    @inline
    def noref_rot_right(self, meta, statelist, amt):
        amt = int(amt) % len(statelist)
        statelist = self.kill_string(statelist, meta)
        return statelist[-amt:] + statelist[:-amt]
    
    @inline
    def noref_rot_left(self, meta, statelist, amt):
        amt = int(amt) % len(statelist)
        statelist = self.kill_string(statelist, meta)
        return statelist[amt:] + statelist[:amt]
    
    def noref_var(self, children, meta):
        ret = []
        m = fix(meta)
        for val in map(self.kill_string, children, repeat(m)):
            if isinstance(val, (tuple, StateList)):
                ret.extend(val)
            elif isinstance(val, int):
                ret.append(int(val))
            else:
                raise Error(fix(meta), val)
        return StateList(ret, context=fix(meta))
    
    def var(self, children, meta):
        m = fix(meta)
        return StateList(self.kill_strings(children, m), context=m)
    
    @inline
    def repeat_int(self, meta, a, b):
        return RepeatInt(self.kill_string(a, meta), int(b), context=meta)
    
    @inline
    def leave_alone_mult(self, meta, underscore, mult):
        return RepeatInt([None], self.kill_string(mult, meta), context=meta)
    
    @inline
    def int_to_var_length(self, meta, num, var):
        return IntToVarLength(int(num), self.kill_string(var, meta), context=meta)
    
    @inline
    def repeat_var(self, meta, var, num):
        return RepeatVar(self.kill_string(var, meta), int(num), context=meta)
    
    @inline
    def subt(self, meta, var, subtrhnd):
        return Subt(self.kill_string(var, meta), StateList(self.kill_string(subtrhnd, meta), context=meta), context=meta)
    
    @inline
    def rot_right(self, meta, var, amt):
        return RotateRight(self.kill_string(var, meta), int(amt), context=meta)
    
    @inline
    def rot_left(self, meta, var, amt):
        return RotateLeft(self.kill_string(var, meta), int(amt), context=meta)
    
    @inline
    def live_except(self, meta, subtrhnd):
        return self.subt(('live', subtrhnd), meta)
    
    @inline
    def all_except(self, meta, subtrhnd):
        return self.subt(('any', subtrhnd), meta)
    
    @inline
    def math_mul(self, meta, a, b):
        return self.kill_string(a, meta, var_and_special=False) * self.kill_string(b, meta, var_and_special=False)
    
    @inline
    def math_div(self, meta, a, b):
        dividend = self.kill_string(b, meta, var_and_special=False)
        if dividend == 0:
            raise ArithmeticErr(meta, f'Cannot divide by 0')
        return self.kill_string(a, meta, var_and_special=False) // dividend
    
    @inline
    def math_add(self, meta, a, b):
        return self.kill_string(a, meta, var_and_special=False) + self.kill_string(b, meta, var_and_special=False)
    
    @inline
    def math_sub(self, meta, a, b):
        return self.kill_string(a, meta, var_and_special=False) - self.kill_string(b, meta, var_and_special=False)
    
    @inline
    def math_nop(self, meta, operand):
        return self.kill_string(operand, meta, var_and_special=False)
    
    @inline
    def math(self, meta, result):
        if result < 0:
            raise ArithmeticErr(meta, f'Arithmetic must result in a positive number, not {result}')
        return result
    
    @inline
    def inline_binding(self, meta, val):
        return InlineBinding(self.kill_string(val, meta), self._tbl, context=meta)
    
    @inline
    def binding(self, meta, cdir):
        if cdir in ('FG', 'BG'):
            return self.rs_binding((cdir,), meta)
        return Binding(self._tbl.check_cdir(cdir, meta, return_int=False, enforce_int=True), context=meta)
    
    @inline
    def mapping(self, meta, cdir, map_to):
        if cdir in ('FG', 'BG'):
            return self.rs_mapping((cdir, map_to), meta)
        return Mapping(self._tbl.check_cdir(cdir, meta, return_int=False, enforce_int=True), self.kill_string(map_to, meta), context=meta)
    
    @inline
    def rs_binding(self, meta, idx):
        # No longer part of the grammar, but
        # should only be called when idx in {'FG', 'BG'}.
        #if idx == '0':
        #    return Binding('0', context=meta)
        return InlineRulestringBinding(str(idx), context=meta)
    
    @inline
    def rs_mapping(self, meta, idx, map_to):
        # No longer part of the grammar, but
        # should only be called when idx in {'FG', 'BG'}.
        #if idx == '0':
        #    return Mapping('0', self.kill_string(map_to, meta), context=meta)
        return InlineRulestringMapping(str(idx), self.kill_string(map_to, meta), context=meta)
    
    @inline
    def rulestring_napkin(self, meta, rulestring, foreground, background):
        return self.modified_rulestring_napkin((rulestring, 'hensel', foreground, background), meta)
    
    @inline
    def modified_rulestring_napkin(self, meta, rulestring, modifier, foreground, background):
        imp = modifier.split('.', 1)
        try:
            func = inline_rulestring.funcs.get(modifier, None) or getattr(import_module(imp[0]), imp[1])
        except (ImportError, ModuleNotFoundError):
            raise UndefinedErr(meta, f"Unknown modifier '{modifier}'")
        return func, {
          'rulestring': str(rulestring),
          'fg': self.kill_string(foreground, meta),
          'bg': self.kill_string(background, meta)
          }
    
    @inline
    def rulestring_tr(self, meta, initial, func__napkin, resultant):
        func, napkin = func__napkin
        args = {
          **napkin,
          'initial': self.kill_string(initial, meta),
          'resultant': self.kill_string(resultant, meta),
          'table': self._tbl,
          'variables': self.vars,
          'meta': meta
        }.items()
        params = signature(func).parameters
        return func(**{k: v for k, v in args if k in params})
        
    
    @inline
    def rulestring_transition(self, meta, trs, aux_first=None, aux_second=None):
        ret = []
        if aux_first is not None and aux_first.meta == 'normal':
            # then, as above, aux_second is either hoisted or nonexistent
            # but in the interest of not doing this conditional every iteration
            # of the below loop, we'll just switch them around here
            aux_second, aux_first = aux_first, aux_second
        for tr in trs:
            ret.extend(chain(tr.apply_aux(aux_first), tr.expand(), tr.apply_aux(aux_second)))
        return ret
