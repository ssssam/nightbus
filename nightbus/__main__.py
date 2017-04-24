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

'''Night Bus: Simple SSH-based build automation'''

import pssh

import argparse
import logging
import os
import sys
import time

import nightbus
from nightbus.utils import ensure_list


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


def name_session():
    return time.strftime('%Y.%m.%d-%H.%M.%S')


def run_single_command(client, hosts, command):
    '''Implements the --command action.'''
    logging.info("Running command %s" % command)
    output = client.run_command(command, stop_on_errors=True)
    client.join(output)
    for host in hosts:
        for line in output[host].stdout:
            print("[%s] %s" % (host, line))
        print("[%s] Exit code: %i" % (host, output[host].exit_code))


def main():
    logging.basicConfig(stream=sys.stdout, level=logging.INFO)

    args = argument_parser().parse_args()

    with open('./tasks') as f:
        tasks = nightbus.tasks.TaskList(f.read())
    with open('./hosts') as f:
        host_config = nightbus.ssh_config.SSHConfig(f.read())

    check_args(args)

    if args.list:
        print("Available hosts:\n\n  *", '\n  * '.join(host_config.keys()))
        print()
        print("Available tasks:\n\n  *", '\n  * '.join(tasks.names()))
        return

    hosts = ensure_list(args.hosts) or host_config.keys()
    tasks_to_run = ensure_list(args.tasks) or tasks.names()
    logging.info("Selected tasks: %s", ','.join(tasks_to_run))

    client = pssh.ParallelSSHClient(hosts, forward_ssh_agent=False, host_config=host_config)

    if args.command:
        run_single_command(client, hosts, args.command)
        return

    session_name = name_session()

    log_directory = os.path.join(args.log_directory, session_name)
    os.makedirs(log_directory, exist_ok=False)
    logging.info("Created log directory: %s", log_directory)

    results = []
    try:
        results = nightbus.tasks.run_all_tasks(
            client, hosts, [t for t in tasks if t.name in tasks_to_run],
            log_directory=log_directory, force=args.force)
    finally:
        if results:
            report_filename = os.path.join(log_directory, 'report')
            logging.info("Writing report to: %s", report_filename)
            with open(report_filename, 'w') as f:
                nightbus.tasks.write_report(f, results)


try:
    main()
except (RuntimeError, pssh.exceptions.ConnectionErrorException,
        pssh.exceptions.AuthenticationException) as e:
    sys.stderr.write("ERROR: %s\n" % e)
    sys.exit(1)
