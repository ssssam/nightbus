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
import collections
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


def safe_filename(filename):
    # If you want to escape more characters, switch to using re.sub()
    return filename.replace('/', '_')


def run_task(client, hosts, task, log_directory, name=None, force=False):
    '''Run a single task on all the specified hosts.'''

    name = name or task['name']
    logging.info("%s: Starting task run", name)

    start_time = time.time()

    # Run the commands asynchronously on all hosts.
    cmd = task['commands']
    shell = task.get('shell')
    if force:
        cmd = 'force=yes\n' + cmd
    output = client.run_command(cmd, shell=shell, stop_on_errors=True)

    # ParallelSSH doesn't give us a way to run a callback when the host
    # produces output or the command completes. In order to stream the
    # output into separate log files, we run a Greenlet to monitor each
    # host.
    def watch_output(output, host):
        log_filename = safe_filename(name + '.' + host + '.log')
        log = os.path.join(log_directory, log_filename)
        with open(log, 'w') as f:
            for line in output[host].stdout:
                f.write(line)
                f.write('\n')
        duration = time.time() - start_time
        exit_code = output[host].exit_code
        return nighttrain.tasks.TaskResult(
            name, host, duration=duration, exit_code=exit_code)

    watchers = [gevent.spawn(watch_output, output, host) for host in hosts]

    gevent.joinall(watchers, raise_error=True)

    logging.info("%s: Started all jobs, waiting for them to finish", name)
    client.join(output)
    logging.info("%s: All jobs finished", name)

    results = [watcher.value for watcher in watchers]
    return {result.host: result for result in results}


def run_all_tasks(client, hosts, tasks, log_directory, force=False):
    '''Loop through each task sequentially.

    We only want to run one task on a host at a time, as we assume it'll
    maximize at least one of available CPU, RAM and IO. However, if fast hosts
    could move onto the next task before slow hosts have finished with the
    previous one it might be nice.

    '''
    all_results = collections.OrderedDict()
    number = 1
    for task in tasks:
        name = '%i.%s' % (number, task['name'])

        result_dict = run_task(
            client, hosts, task, log_directory=log_directory,
            name=name, force=force)

        all_results[name] = result_dict

        failed_hosts = [t.host for t in result_dict.values() if t.exit_code!=0]

        if failed_hosts:
            msg = "Task %s failed on: %s" % (
                name, ', '.join(failed_hosts))
            logging.error(msg)
            raise RuntimeError(msg)

        number += 1
    return all_results


def duration_as_string(seconds):
    m, s = divmod(seconds, 60)
    h, m = divmod(m, 60)
    return ("%d:%02d:%02d" % (h, m, s))


def write_report(filename, all_results):
    '''Write a report containing task results and durations.'''
    with open(filename, 'w') as f:
        first_line = True
        for task_name, task_results in all_results.items():
            if first_line:
                first_line = False
            else:
                f.write("\n")

            f.write("%s:\n", task_name)

            for host, result in task_results.items():
                status = "succeeded" if result.exit_code == 0 else "failed"
                duration = duration_as_string(result.duration)
                f.write("  - %s: %s in %s\n" % (host, status, duration))


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

    session_name = name_session()

    log_directory = os.path.join(args.log_directory, session_name)
    os.makedirs(log_directory, exist_ok=False)
    logging.info("Created log directory: %s", log_directory)

    results = []
    try:
        results = run_all_tasks(
            client, hosts, [t for t in tasks if t['name'] in tasks_to_run],
            log_directory=log_directory, force=args.force)
    finally:
        if results:
            report_filename = os.path.join(log_directory, 'report')
            logging.info("Writing report to: %s", report_filename)
            write_report(report_filename, results)


try:
    main()
except (RuntimeError, pssh.exceptions.ConnectionErrorException) as e:
    sys.stderr.write("ERROR: %s\n" % e)
    sys.exit(1)
