#!/bin/bash
#
# Run continuous build tasks.
#
# Usage:
#   ./toil-worker.sh <function name>

set -o nounset
set -o pipefail
set -o errexit

source services/common.sh

time-tsv() {
  benchmarks/time_.py --tsv "$@"
}

dummy() {
  echo 'dummy task with env:'
  echo

  # mangles multi-line values, but that's OK here
  dump-env
}

dummy-tasks() {
  ### Print tasks that execute quickly

  # (task_name, script, action, result_html)
  cat <<EOF
dummy           services/toil-worker.sh dummy  -
EOF
}

run-dummy() {
  dummy-tasks | run-tasks
}

dev-minimal-tasks() {
  ### Print tasks for the 'dev-minimal' build

  # (task_name, script, action, result_html)
  cat <<EOF
build-minimal   build/dev.sh minimal        -
lint            test/lint.sh travis         -
typecheck-slice types/oil-slice.sh travis   -
typecheck-other types/run.sh travis         -
unit            test/unit.sh travis         -
oil-spec        test/spec.sh oil-all-serial _tmp/spec/oil.html
osh-spec        test/spec.sh osh-travis     _tmp/spec/osh.html
EOF
}

dev-all-nix-tasks() {
  ### Print tasks for the 'dev-all' build

  # (task_name, script, action, result_html)
  cat <<EOF
build-all       build/dev.sh all            -
oil-spec        test/spec.sh oil-all-serial _tmp/spec/oil.html
osh-spec        test/spec.sh osh-travis     _tmp/spec/osh.html
EOF
}


# https://github.com/oilshell/oil/wiki/Contributing

ovm-tarball-tasks() {
  ### Print tasks for the 'ovm-tarball' build

  # (task_name, script, action, result_html)
  cat <<EOF
cpython-configure build/prepare.sh configure             -
cpython-build     build/prepare.sh build-python          -
download-re2c     build/codegen.sh download-re2c         -
install-re2c      build/codegen.sh install-re2c          -
install-cmark     doctools/cmark.sh travis-setup         -
build-all         build/dev.sh all                       -
make-tarball      devtools/release.sh quick-oil-tarball  -
build-tarball     build/test.sh oil-tar                  -
EOF

  # TODO: cache 
  # -_devbuild/cpython-full  # rarely changes
  # -_deps/                  # re2c rarely changes
}

run-tasks() {
  ### Run the tasks on stdin and write _tmp/toil/INDEX.tsv.

  local out_dir=_tmp/toil
  mkdir -p $out_dir

  # This data can go on the dashboard index
  local tsv=$out_dir/INDEX.tsv
  rm -f $tsv

  while read task_name script action result_html; do
    log "--- task: $task_name ---"

    local log_path=$out_dir/$task_name.log.txt 

    set +o errexit
    time-tsv -o $tsv --append --field $task_name --field $script --field $action --field $result_html -- \
      $script $action >$log_path 2>&1
    set -o errexit

    # show the last line

    echo
    echo $'status\telapsed\ttask\tscript\taction\tresult_html'
    tail -n 1 $tsv
    echo
  done

  log '--- done ---'
  wc -l $out_dir/*

  # This suppressed the deployment of logs, which we don't want.  So all our
  # Travis builds succeed?  But then we can't use their failure notifications
  # (which might be OK).
  if false; then
    # exit with the maximum exit code.
    awk '
    BEGIN { max = 0 }
          { if ($1 > max) { max = $1 } }
    END   { exit(max) }
    ' _tmp/toil/INDEX.tsv
  fi
}

run-dev-minimal() {
  ### Travis job dev-minimal

  #export TRAVIS_SKIP=1
  dev-minimal-tasks | run-tasks
}

_run-dev-all-nix() {
  dev-all-nix-tasks | run-tasks
  return

  # --- DEBUGGING THROUGH STDOUT ---

  # makes _tmp
  build/dev.sh all

  # So we have something to deploy
  dummy-tasks | run-tasks

  if false; then
    test/spec.sh check-shells-exist
    # this hangs because nix bash doesn't have 'compgen' apparently
    test/spec.sh builtin-completion -v -t
  fi

  test/spec.sh osh-travis

}

run-ovm-tarball() {
  ovm-tarball-tasks | run-tasks
}

run-dev-all-nix() {
  ### Travis job dev-all-nix

  # Run tasks the nix environment
  nix-shell \
    --argstr dev "none" \
    --argstr test "none" \
    --argstr cleanup "none" \
    --run "$0 _run-dev-all-nix"
}

"$@"
