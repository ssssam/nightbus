# Night Train: Simple SSH-based build automation

Night Train is a minimalist build automation tool. It requires nothing on the
build machines but a shell, an SSH server and your build dependencies.
It's intended for automating slow processes that need to run on multiple
machines and was written initially for building and testing the GNU toolchain
on various architectures<sup>1</sup>.

Night Train is written in Python 3, and reads configuration from YAML format
files. It's built on top of the
[ParallelSSH](https://github.com/ParallelSSH/parallel-ssh) library. It's
heavily inspired by the
[Ansible](https://en.wikipedia.org/wiki/Ansible_(software)) configuration
management tool, with the main difference being that Night Train provides
real-time logging of the tasks as they execute.

*1. including the old proprietary platforms where dependency hell is still a
thing and where lots of modern tools don't even work....*

## Installation

Right now the software should be used directly from Git. It's early days.

    # Install dependencies if needed... `pip3 install --user gevent paramiko pyyaml`
    git clone --recursive git://github.com/ssssam/nighttrain

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

    ../nightrain/run.py --command 'echo "Hello from $(hostname)"'

### Tasks

Now you describe what tasks need to be run. This is done using a file named
`tasks` which contains an ordered list of tasks.

```
- name: gcc-incremental-build-and-test
  description: Run an incremental build of GCC
  commands: |
    set -e

    sourcedir=~/autobuild/gcc-incremental
    repo=git://github.com/gcc-mirror/gcc.git
    remote=origin
    track=master

    # Update our clone of mainline gcc.git, and exit if there are no changes
    # FIXME: a `git clone-or-update` wrapper would make this neater.
    echo "Updating clone of $repo branch $track"
    mkdir -p $sourcedir; cd $sourcedir
    if [ -e '.git' ]; then
        git remote set-url $remote $repo
        git checkout -B $track $remote/$track
        output=$(git pull $remote $track)
        if echo $output | grep -q 'Already up-to-date' && [ "$force" != "yes" ] ; then
            echo "No changes in remote Git repo, exiting."
            exit 0;
        fi
    else
        git clone $repo --branch=$track --origin $remote .
    fi

    configure_args="--enable-languages=c,c++,fortran --disable-bootstrap"

    echo "Running build"
    mkdir -p build
    cd build
    ../configure $configure_args
    gmake

    echo "Running test suite"
    gmake check

- name: gcc-package
  description: Run a clean package build of GCC
  commands: |
    # Commands go here to build a package of whatever format...
```

A task set executes one at a time. So first 'gcc-incremental-build-and-test' runs
on all hosts. If any hosts fail, the sequences is aborted once the last host has
finished. If the test was successful, all hosts start the next task 'gcc-package'.

We need a directory to store logs for the tasks. For testing, create one in the
current directory, and then run the tasks:

    mkdir logs
    ../nighttrain/run.py --log-directory=./logs

You should see files like this inside the `./logs` directory:

    ./logs/2017.03.21-18.44.00-gcc-incremental-build-and-test/host1.log
    ./logs/2017.03.21-18.44.00-gcc-incremental-build-and-test/host2.log

You can `tail -f` these to see how your build is going.

There are some commandline options to help you debug tasks:

  * `--command`: run a single command on all hosts
  * `--force`: adds `force=yes` as the first line of the task.
  * `--tasks`: select a subset of tasks to be executed

### Deployment

To make logs browsable outside the machine running Night Train, install a
web server and set the log directory to somewhere inside `/var/www`.

To start your builds at a specific time, use Cron or a systemd .timer unit
to execute the `run.py` script appropriately.

## Goals

We like ...

 * ... a small, tidy codebase
 * ... a clean, convenient commandline interface
 * ... no special requirements on the build machines

## Common issues

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
