#!/usr/bin/env python2
"""
time.py -- Replacement for coreutils 'time'.

The interface of this program is modelled after:

/usr/bin/time --append --output foo.txt --format '%x %e'

Problems with /usr/bin/time:
  - elapsed time only has 2 digits of precision

Problems with bash time builtin
  - has no way to get the exit code
  - writes to stderr, so you it's annoying to get both process stderr and
    and

This program also writes CSV directly, so you can have commas in fields, etc.
"""
from __future__ import print_function

import csv
import optparse
import resource
import sys
import subprocess
import time


def log(msg, *args):
  if args:
    msg = msg % args
  print(msg, file=sys.stderr)


def Options():
  """Returns an option parser instance."""
  p = optparse.OptionParser('time.py [options] ARGV...')
  p.add_option(
      '--tsv', dest='tsv', default=False, action='store_true',
      help='Write output in TSV format')
  p.add_option(
      '--rusage', dest='rusage', default=False, action='store_true',
      help='Also show user time, system time, and max resident set size')
  p.add_option(
      '-o', '--output', dest='output', default=None,
      help='Name of output file to write to to')
  p.add_option(
      '-a', '--append', dest='append', default=False, action='store_true',
      help='Append to the file instead of overwriting it')
  p.add_option(
      '--field', dest='fields', default=[], action='append',
      help='A string to append to each row, after the exit code and status')
  p.add_option(
      '--time-fmt', dest='time_fmt', default='%.4f',
      help='sprintf format for elapsed seconds (float)')
  p.add_option(
      '--stdout', dest='stdout', default=None,
      help='Save stdout to this file, and add a column for its md5 checksum')
  return p


def main(argv):
  (opts, child_argv) = Options().parse_args(argv[1:])

  if not child_argv:
    log('time.py: Expected a command')
    return 2

  start_time = time.time()
  try:
    if opts.stdout:
      with open(opts.stdout, 'w') as f:
        exit_code = subprocess.call(child_argv, stdout=f)
    else:
      exit_code = subprocess.call(child_argv)
  except OSError as e:
    log('Error executing %s: %s', child_argv, e)
    return 1

  if opts.rusage:
    r = resource.getrusage(resource.RUSAGE_CHILDREN)
    rusage_fields = [r.ru_utime, r.ru_stime, r.ru_maxrss]
  else:
    rusage_fields = []

  elapsed = time.time() - start_time
  if opts.stdout:
    import md5
    m = md5.new()
    with open(opts.stdout) as f:
      while True:
        chunk = f.read(4096)
        if not chunk:
          break
        m.update(chunk)
    maybe_stdout = [m.hexdigest()]
  else:
    maybe_stdout = []  # no field

  row = (
      [exit_code, opts.time_fmt % elapsed] + rusage_fields + maybe_stdout +
      opts.fields
  )

  if opts.output:
    mode = 'a' if opts.append else 'w'
    with open(opts.output, mode) as f:
      if opts.tsv:
        # TSV output.
        out = csv.writer(f, delimiter='\t', lineterminator='\n',
                         doublequote=False,
                         quoting=csv.QUOTE_NONE)
      else:
        out = csv.writer(f)
      out.writerow(row)
  else:
    log("time.py wasn't passed -o: %s", row)

  # Preserve the command's exit code.  (This means you can't distinguish
  # between a failure of time.py and the command, but that's better than
  # swallowing the error.)
  return exit_code


if __name__ == '__main__':
  sys.exit(main(sys.argv))
