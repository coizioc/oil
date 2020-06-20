#!/usr/bin/env python2
"""
flag_gen.py
"""
from __future__ import print_function

import sys

from _devbuild.gen.runtime_asdl import flag_type_e, value_e
from core.pyerror import log
from frontend import args
from frontend import flag_def  # side effect: flags are defined!
from frontend import flag_spec
from mycpp.mylib import tagswitch
# This causes a circular build dependency!  That is annoying.
# builtin_comp -> core/completion -> pylib/{os_path,path_stat,...} -> posix_
#from osh import builtin_comp


def CString(s):
  # HACK for now
  assert '"' not in s, s
  assert '\\' not in s, s

  return '"%s"' % s


def Cpp(specs, header_f, cc_f):
  header_f.write("""\
// arg_types.h is generated by frontend/flag_gen.py

#ifndef ARG_TYPES_H
#define ARG_TYPES_H

#include "frontend_flag_spec.h"  // for FlagSpec_c
#include "mylib.h"

namespace value_e = runtime_asdl::value_e;
using runtime_asdl::value__Bool;
using runtime_asdl::value__Int;
using runtime_asdl::value__Str;

namespace arg_types {
""")
  for spec_name in sorted(specs):
    spec = specs[spec_name]

    if not spec.fields:
      continue  # skip empty 'eval' spec

    header_f.write("""
class %s {
 public:
  %s(Dict<Str*, runtime_asdl::value_t*>* attrs) :
""" % (spec_name, spec_name))

    init_vals = []
    field_decls = []
    for field_name in sorted(spec.fields):
      typ = spec.fields[field_name]

      with tagswitch(typ) as case:
        if case(flag_type_e.Bool):
          init_vals.append('static_cast<value__Bool*>(attrs->index(new Str("%s")))->b' % field_name)
          field_decls.append('bool %s;' % field_name)

        elif case(flag_type_e.Str, flag_type_e.Enum):
          default_val = spec.defaults[field_name]
          with tagswitch(default_val) as case:
            if case(value_e.Undef):
              default_str = 'nullptr'
            elif case(value_e.Str):
              default_str = 'new Str("%s")' % default_val.s
            else:
              raise AssertionError()

          # TODO: This code is ugly and inefficient!  Generate something
          # better.  At least get rid of 'new' everywhere?
          init_vals.append('''\
attrs->index(new Str("%s"))->tag_() == value_e::Undef
      ? %s
      : static_cast<value__Str*>(attrs->index(new Str("%s")))->s''' % (
              field_name, default_str, field_name))

          field_decls.append('Str* %s;' % field_name)

        elif case(flag_type_e.Int):
          init_vals.append('''\
attrs->index(new Str("%s"))->tag_() == value_e::Undef
      ? -1
      : static_cast<value__Int*>(attrs->index(new Str("%s")))->i''' % (field_name, field_name))
          field_decls.append('int %s;' % field_name)

        else:
          raise AssertionError(typ)

    for i, field_name in enumerate(sorted(spec.fields)):
      if i != 0:
        header_f.write(',\n')
      header_f.write('    %s(%s)' % (field_name, init_vals[i]))
    header_f.write(' {\n')
    header_f.write('  }\n')

    for decl in field_decls:
      header_f.write('  %s\n' % decl)

    header_f.write("""\
};
""")

  header_f.write("""
extern FlagSpec_c kFlagSpecs[];
extern FlagSpecAndMore_c kFlagSpecsAndMore[];

}  // namespace arg_types

#endif  // ARG_TYPES_H

""")

  cc_f.write("""\
// arg_types.cc is generated by frontend/flag_gen.py

#include "arg_types.h"

namespace arg_types {

""")

  var_names = []
  for i, spec_name in enumerate(sorted(flag_spec.FLAG_SPEC)):
    spec = specs[spec_name]
    arity0_name = None
    arity1_name = None
    options_name = None
    defaults_name = None

    if spec.arity0:
      arity0_name = 'arity0_%d' % i
      c_strs = ', '.join(CString(s) for s in sorted(spec.arity0))
      cc_f.write('const char* %s[] = {%s, nullptr};\n' % (arity0_name, c_strs))

    if spec.arity1:
      arity1_name = 'arity1_%d' % i
      cc_f.write('SetToArg_c %s[] = {\n' % arity1_name)
      for name in sorted(spec.arity1):
        set_to_arg = spec.arity1[name]

        # Using an integer here
        # TODO: doesn't work for enum flag_type::Enum(...)
        f2 = set_to_arg.flag_type.tag_()

        cc_f.write('    {"%s", %s, %s},\n' % (name, f2, 'true' if set_to_arg.quit_parsing_flags else 'false'))
      #cc_f.write('SetToArg_c %s[] = {\n' % arity1_name)
      cc_f.write('''\
    {},
};
''')

    if spec.options:
      options_name = 'options_%d' % i
      c_strs = ', '.join(CString(s) for s in sorted(spec.options))
      cc_f.write('const char* %s[] = {%s, nullptr};\n' % (options_name, c_strs))

    if spec.defaults:
      defaults_name = 'defaults_%d' % i
      cc_f.write('DefaultPair_c %s[] = {\n' % defaults_name)
      for name in sorted(spec.defaults):
        val = spec.defaults[name]
        if val.tag_() == value_e.Bool:
          d = 'True' if val.b else 'False'
        elif val.tag_() == value_e.Int:
          d = 'Undef'  # TODO: fix this.  Should be -1
        elif val.tag_() == value_e.Undef:
          d = 'Undef'

        # NOTE: 'osh' FlagSpecAndMore_ has default='nice' and default='abbrev-text'
        else:
          raise AssertionError(val)

        cc_f.write('    {%s, Default_c::%s},\n' % (CString(name), d))

      cc_f.write('''\
    {},
};
''')
    var_names.append((arity0_name, arity1_name, options_name, defaults_name))
    cc_f.write('\n')

  cc_f.write('FlagSpec_c kFlagSpecs[] = {\n')

  # Now print a table
  for i, spec_name in enumerate(sorted(flag_spec.FLAG_SPEC)):
    spec = specs[spec_name]
    names = var_names[i]
    cc_f.write('    { "%s", %s, %s, %s, %s },\n' % (
      spec_name,
      names[0] or 'nullptr', 
      names[1] or 'nullptr', 
      names[2] or 'nullptr', 
      names[3] or 'nullptr', 
    ))

  cc_f.write("""\
    {},
};

""")

  var_names = []
  for i, spec_name in enumerate(sorted(flag_spec.FLAG_SPEC_AND_MORE)):
    spec = specs[spec_name]
    actions_short_name = None
    actions_long_name = None
    defaults_name = None

    if spec.actions_short:
      actions_short_name = 'short_%d' % i
      cc_f.write('Action_c %s[] = {\n' % actions_short_name)
      for name in sorted(spec.actions_short):
        action = spec.actions_short[name]
        log('%s %s', name, action)
        if isinstance(action, args.SetToArgAction):
          set_to_arg = action.action
          f2 = set_to_arg.flag_type.tag_()

          action_type = 'ActionType_c::SetToArg'
          cc_f.write('    {%s, "%s", %s, %s},\n' % (action_type, name, f2, 'true' if set_to_arg.quit_parsing_flags else 'false'))
        elif isinstance(action, args.SetToTrue):
          log('action %s', action.name)
      cc_f.write('''\
    {},
};

''')

    #if spec.actions_long:
    if 0:
      actions_long_name = 'long_%d' % i
      cc_f.write('Action_c %s[] = {\n' % actions_long_name)
      for name in sorted(spec.actions_long):
        action = spec.actions_long[name]
        if isinstance(action, args.SetToArgAction):
          a = action.action
          log('action %s %s', name, a.name)
        elif isinstance(action, args.SetToTrue):
          log('action %s %s', name, action.name)

    var_names.append((actions_short_name, actions_long_name, defaults_name))

  cc_f.write('FlagSpecAndMore_c kFlagSpecsAndMore[] = {\n')
  for i, spec_name in enumerate(sorted(flag_spec.FLAG_SPEC_AND_MORE)):
    names = var_names[i]
    cc_f.write('    { "%s", %s, %s, %s },\n' % (
      spec_name,
      names[0] or 'nullptr', 
      names[1] or 'nullptr', 
      names[2] or 'nullptr', 
    ))

  cc_f.write("""\
    {},
};
""")

  cc_f.write("""\
}  // namespace arg_types
""")


def main(argv):
  try:
    action = argv[1]
  except IndexError:
    raise RuntimeError('Action required')

  if 0:
    for spec_name in sorted(flag_spec.FLAG_SPEC_AND_MORE):
      log('%s', spec_name)

  # Both kinds of specs have 'fields' attributes
  specs = {}
  specs.update(flag_spec.FLAG_SPEC)
  specs.update(flag_spec.FLAG_SPEC_AND_MORE)

  log('--')
  for spec_name in sorted(specs):
    spec = specs[spec_name]
    #spec.spec.PrettyPrint(f=sys.stderr)
    #log('spec.arity1 %s', spec.spec.arity1)
    log('%s', spec_name)

    #print(dir(spec))
    #print(spec.arity0)
    #print(spec.arity1)
    #print(spec.options)
    # Every flag has a default
    #log('%s', spec.fields)

  if action == 'cpp':
    prefix = argv[2]

    with open(prefix + '.h', 'w') as header_f:
      with open(prefix + '.cc', 'w') as cc_f:
        Cpp(specs, header_f, cc_f)

  elif action == 'mypy':
    print("""
from frontend.args import _Attributes
from _devbuild.gen.runtime_asdl import (
   value, value_e, value_t, value__Bool, value__Int, value__Float, value__Str,
)
from typing import cast, Dict, Optional
""")
    for spec_name in sorted(specs):
      spec = specs[spec_name]

      #log('%s spec.fields %s', spec_name, spec.fields)
      if not spec.fields:
        continue  # skip empty specs, e.g. eval

      print("""
class %s(object):
  def __init__(self, attrs):
    # type: (Dict[str, value_t]) -> None
""" % spec_name)

      i = 0
      for field_name in sorted(spec.fields):
        typ = spec.fields[field_name]

        with tagswitch(typ) as case:
          if case(flag_type_e.Bool):
            print('    self.%s = cast(value__Bool, attrs[%r]).b  # type: bool' % (
              field_name, field_name))

          # enums are strings for now
          elif case(flag_type_e.Str, flag_type_e.Enum):
            tmp = 'val%d' % i
            default_val = spec.defaults[field_name]
            with tagswitch(default_val) as case:
              if case(value_e.Undef):
                default_str = 'None'
              elif case(value_e.Str):
                default_str = '%r' % default_val.s
              else:
                raise AssertionError()
            print('    %s = attrs[%r]' % (tmp, field_name))
            print('    self.%s = %s if %s.tag_() == value_e.Undef else cast(value__Str, %s).s  # type: Optional[str]' % (field_name, default_str, tmp, tmp))

          elif case(flag_type_e.Int):
            tmp = 'val%d' % i
            print('    %s = attrs[%r]' % (tmp, field_name))
            print('    self.%s = -1 if %s.tag_() == value_e.Undef else cast(value__Int, %s).i  # type: int' % (field_name, tmp, tmp))

          else:
            raise AssertionError(typ)

        i += 1

      print()

  else:
    raise RuntimeError('Invalid action %r' % action)


if __name__ == '__main__':
  try:
    main(sys.argv)
  except RuntimeError as e:
    print('FATAL: %s' % e, file=sys.stderr)
    sys.exit(1)
