# Night Bus: Simple SSH-based build automation

Night Bus is a minimalist build automation tool. It requires nothing on the
build machines but a shell, an SSH server and your build dependencies.
It's intended for automating slow processes that need to run on multiple
machines and was written initially for building and testing the GNU toolchain
on various architectures<sup>1</sup>.

Night Bus is written in Python 3, and reads configuration from YAML format
files. It's built on top of the
[ParallelSSH](https://github.com/ParallelSSH/parallel-ssh) library. It's
heavily inspired by the
[Ansible](https://en.wikipedia.org/wiki/Ansible_(software)) configuration
management tool, with the main difference being that Night Bus provides
real-time logging of the tasks as they execute.

*1. including the old proprietary platforms where dependency hell is still a
thing and where lots of modern tools don't even work....*

## Installation

Right now the software should be used directly from Git. It's early days.

    # Install dependencies if needed... `pip3 install --user gevent paramiko pyyaml`
    git clone --recursive git://github.com/ssssam/nightbus

## Configuration

Now set up the configuration that you want. We recommend doing this in a
separate directory or perhaps a Git repo.

### Hosts

First you need to describe how to access all of the build machines. This
is done using a file named `hosts`. Here's an example:

```
host1:
  user: automation
  private_key: ssh/automation.key

host2:
  proxy_host: 86.75.30.9
  proxy_user: jenny
  proxy_private_key: ssh/jenny.key
```

The parameters are passed as in the
[ParallelSSHClient constructor](https://parallel-ssh.readthedocs.io/en/latest/pssh_client.html),
except for pkey -> private_key.

You can test your host configuration by running a test command:

    ../nightbus/run.py --command 'echo "Hello from $(hostname)"'

### Tasks

Now you describe what tasks need to be run. This is done using a file named
`tasks` which contains an ordered list of tasks.

Here's a simple task file with one pointless task.

```
tasks:
- name: counting-example
  commands: |
    echo "Counting to 20."
    for i in `seq 1 20`; do
      echo "Hello $i"
      sleep 1
    done
```

When you run this it'll count to 20 on every host. You can see the results
on stdout or in the log files in the log directory.

Here's a more advanced example, with some inline comments explaining it.

```
defaults:
  # Night Bus comes with a library of shell functions that allow you to write
  # clearer tasks. You can include anything you want here and it'll be
  # prepended to each task.
  include:
    - nightbus/library.sh

tasks:
- name: gcc-rebuild
  description: Run a build of GCC, reusing an existing build tree if present.
  commands: |
    set -e

    sourcedir=~/autobuild/gcc-incremental
    repo=git://github.com/gcc-mirror/gcc.git
    remote=origin
    track=master

    echo "Updating clone of $repo branch $track"

    # This helper function comes from nightbus/library.sh and is documented
    # there. It will clone the repo if necessary and update it if necessary.
    # It returns false if there were no new changes.
    if ensure_uptodate_git_branch_checkout "$sourcedir" "$remote" "$repo" "$track" \
            || [ "$force" = "yes" ] ; then
        # This only runs if there were new changes in the repo, or if the user
        # passed `--force` to Night Bus.
        cd $sourccedir
        configure_args="--enable-languages=c,c++ --disable-bootstrap"

        echo "Running build"
        mkdir -p build
        cd build
        ../configure $configure_args
        gmake
    else
        echo "No changes in remote Git repo, exiting."
        exit 0
    fi

- name: gcc-test
  description: Runs the GCC test suite.
  commands: |
    set -e

    sourcedir=~/autobuild/gcc-incremental
    cd $sourcedir/build

    echo "Running test suite"
    gmake check
```

A task set executes one at a time. So first 'gcc-rebuild' runs on all hosts. If
any hosts fail, the sequences is aborted once the last host has finished. If
the test was successful, all hosts start the next task 'gcc-test'.

We need a directory to store logs for the tasks. For testing, create one in the
current directory, and then run the tasks:

    mkdir logs
    ../nightbus/run.py --log-directory=./logs

You should see files like this inside the `./logs` directory:

    ./logs/2017.03.21-18.44.00-gcc-incremental-build-and-test/host1.log
    ./logs/2017.03.21-18.44.00-gcc-incremental-build-and-test/host2.log

You can `tail -f` these to see how your build is going.

There are some commandline options to help you debug tasks:

  * `--command`: run a single command on all hosts
  * `--ignore-errors`: continue running tasks even if some have failed
  * `--force`: adds `force=yes` as the first line of the task.
  * `--tasks`: select a subset of tasks to be executed

### Deployment

To make logs browsable outside the machine running Night Bus, install a
web server and set the log directory to somewhere inside `/var/www`.

To start your builds at a specific time, use Cron or a systemd .timer unit
to execute the `run.py` script appropriately.

### Advanced features

Night Bus supports *parameterization* of tasks. This is inspired by similar
features in other tools such as [pytest](https://www.pytest.org/).

This input will result in three tasks being generated:

```
- name: example
  parameters:
    person: ['Eleanor', 'Matthew', 'Bill']
  commands: |
    echo "Hello, $person"
```

You can run nightbus `--list` and see them for example:

  * example-Eleanor
  * example-Matthew
  * example-Bill

Multiple parameters can be specified, but beware that the code will
probably not scale well if you start generating hundreds of tasks this way!
Instead of passing a string for the value, you can pass a dict like this:

    { repr: default, value: '' }

The 'repr' value is used in the task name, while the 'value' is what gets
used in the task. This is useful if the values you're working with contain
characters that aren't valid in task names for example.

## Goals

We like ...

 * ... a small, tidy codebase
 * ... a clean, convenient commandline interface
 * ... no special requirements on the build machines
 * ... shell scripts which are smaller than 10 lines and can be read at a glance

## Common issues

### Debugging errors is hard

Add `set -x` to the top of your task so that the shell prints out each command
it runs before running it.

### The tasks don't use the correct PATH, so some programs aren't found

By default, Bash ignores your .profile and .bashrc files when running
scripts. If you find that annoying, you can set this option for a task:

    `shell: bash -i -l -c`

This tells Bash to behave the same way when running that task as it does would
in your interactive SSH session. [Read more
here](https://www.gnu.org/software/bash/manual/html_node/Bash-Startup-Files.html).

## Known problems

We use a fork of Parallel-SSH, due to needing a better fix for:
https://github.com/ParallelSSH/parallel-ssh/pull/78

## Why not use...

### Ansible or Fabric?

Ansible can't give us live output from the tasks, it just sends the whole log
over once the task completes. For jobs that can take hours and hours like
running the GCC test suite this is a major limitation.

At time of writing the Ansible team have looked at adding this feature and
decided against it: https://github.com/ansible/ansible/issues/3887

Fabric also appears not to have such a feature, and no discussion of it.

[cdist](http://www.nico.schottelius.org/software/cdist/)
also has nice aspects but its design really ties it to doing configuration management 
rather than build+test automation.

### BuildBot?

I would recommend [BuildBot](https://buildbot.net/) as the "next step up" from Night Bus.

### Gitlab CI?

Gitlab CI requires a [client program written in Go](https://gitlab.com/gitlab-org/gitlab-ci-multi-runner) on each build machine. Go is not supported on every platform, for example [AIX](https://groups.google.com/forum/#!topic/golang-nuts/ByTFX0mxloE).

## License

Copyright 2017 Codethink Ltd.

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
