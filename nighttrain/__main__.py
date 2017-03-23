# Copyright 2017 Codethink Ltd.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

'''Night Train: Simple SSH-based build automation'''

import gevent
import pssh

import argparse
import logging
import os
import sys
import time

import nighttrain


def argument_parser():
    parser = argparse.ArgumentParser(
        description="Simple SSH automation for build, test, deployment, etc.")
    # Controls for running tasks
    parser.add_argument(
        '--force', action='store_true',
        help="Define 'force=yes' in environment for each task")
    parser.add_argument(
        '--hosts', '--host', type=str,
        help="Select hosts to run on (default: all hosts)")
    parser.add_argument(
        '--tasks', '--task', '-t', type=str,
        help="Select tasks to run (default: all tasks)")
    parser.add_argument(
        '--log-directory', '-l', type=str, default='/var/log/ci',
        help="Base directory for log files")
    # Alternative actions
    parser.add_argument(
        '--command', '-c', type=str, default=None,
        help="Run the specified command on the remote hosts, instead of any "
             "of the tasks. This is intended for debugging your tasks.")
    parser.add_argument(
        '--list', action='store_true',
        help="List the available tasks and hosts, then exit")
    return parser


def check_args(args):
    normal_run = True

    if args.command:
        normal_run = False
        if args.list:
            raise RuntimeError("--command and --list are incompatible")
        if args.tasks:
            raise RuntimeError("--command and --tasks are incompatible")

    if args.list:
        normal_run = False
        if args.tasks:
            raise RuntimeError("--list and --tasks are incompatible")

    if normal_run:
        if not os.path.isdir(args.log_directory):
            raise RuntimeError("Log directory %s doesn't seem to exist. "
                               "Use --log-directory to change." %
                               args.log_directory)
        if not os.access(args.log_directory, os.W_OK):
            raise RuntimeError("Log directory %s doesn't appear writable" %
                               args.log_directory)


def ensure_list(string_or_list):
    if isinstance(string_or_list, str):
        return [string_or_list]
    else:
        return string_or_list


def name_task_run(task_name):
    return time.strftime('%Y.%m.%d-%H.%M.%S-' + task_name)


def run_single_command(client, hosts, command):
    '''Implements the --command action.'''
    logging.info("Running command %s" % command)
    output = client.run_command(command, stop_on_errors=True)
    client.join(output)
    for host in hosts:
        for line in output[host].stdout:
            print("[%s] %s" % (host, line))
        print("[%s] Exit code: %i" % (host, output[host].exit_code))


def run_task(client, hosts, task, log_directory, force=False):
    '''Run a single task on all the specified hosts.'''
    task_run_name = name_task_run(task['name'])
    logging.info("%s: Starting task run", task_run_name)

    log_dir = os.path.join(log_directory, task_run_name)
    os.makedirs(log_dir, exist_ok=False)
    logging.info("%s: Created log directory: %s", task_run_name, log_dir)

    # Run the commands asynchronously on all hosts.
    cmd = task['commands']
    shell = task.get('shell')
    if force:
        cmd = 'force=yes\n' + cmd
    output = client.run_command(cmd, shell=shell, stop_on_errors=True)

    # ParallelSSH doesn't give us a way to run a callback for each line of
    # output received. It does have an internal logger for the remote output
    # but there's no clean way to divide the output into different files. We
    # could chain or zip the generators we receive but that way we'll only
    # receive output at the speed that the slowest host sends it back. Instead,
    # we use GEvent Greenlets to read the output for each host independently.
    # Think of it as like threads except they're not.
    #
    # The output is still all buffered into memory by ParallelSSH which is not
    # ideal for long running GCC builds and such.
    def log_output(output, host):
        log = os.path.join(log_dir, host + '.log')
        with open(log, 'w') as f:
            for line in output[host].stdout:
                f.write(line)
                f.write('\n')

    read_jobs = [gevent.spawn(log_output, output, host) for host in hosts]

    gevent.joinall(read_jobs)

    logging.info("%s: Started all jobs, waiting for them to finish",
        task_run_name)
    client.join(output)
    logging.info("%s: All jobs finished", task_run_name)

    failed_hosts = [host for host in hosts if output[host].exit_code != 0]
    if failed_hosts:
        msg = "Task %s failed on: %s" % (task_run_name,
                                         ', '.join(failed_hosts))
        logging.error(msg)
        raise RuntimeError(msg)


def main():
    logging.basicConfig(stream=sys.stdout, level=logging.INFO)

    args = argument_parser().parse_args()

    tasks = nighttrain.tasks.TaskList('./tasks')
    host_config = nighttrain.ssh_config.SSHConfig('./hosts')

    check_args(args)

    if args.list:
        print("Available hosts:\n\n  *", '\n  * '.join(host_config.keys()))
        print()
        print("Available tasks:\n\n  *", '\n  * '.join(tasks.names()))
        return

    hosts = ensure_list(args.hosts) or host_config.keys()
    tasks_to_run = ensure_list(args.tasks) or tasks.names()
    logging.info("Selected tasks: %s", ','.join(tasks_to_run))

    client = pssh.ParallelSSHClient(hosts, host_config=host_config)

    if args.command:
        run_single_command(client, hosts, args.command)
        return

    # Loop through each task sequentially. We only want to run one task on a
    # host at a time, as we assume it'll maximize at least one of available CPU,
    # RAM and IO. However, if fast hosts could move onto the next task before
    # slow hosts have finished with the previous one it might be nice.
    for task in tasks:
        if task['name'] in tasks_to_run:
            run_task(client, hosts, task,
                log_directory=args.log_directory, force=args.force)


try:
    main()
except (RuntimeError, pssh.exceptions.ConnectionErrorException) as e:
    sys.stderr.write("ERROR: %s\n" % e)
    sys.exit(1)
