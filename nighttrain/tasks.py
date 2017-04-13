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
import yaml

import collections
import logging
import os
import time

import nighttrain
from nighttrain.utils import ensure_list


class TaskList(list):
    '''Contains a user-specified list of descriptions of tasks to run.'''
    def __init__(self, text):
        contents = yaml.safe_load(text)
        if isinstance(contents, list):
            self.extend(contents)
        elif isinstance(contents, dict):
            self.extend(contents['tasks'])
        else:
            raise RuntimeError("Tasks file is invalid.")

    def names(self):
        return [task['name'] for task in self]


class TaskResult():
    '''Results of executing a one task on one host.'''
    def __init__(self, name, host, duration=None, exit_code=None):
        self.name = name
        self.host = host
        self.duration = duration
        self.exit_code = exit_code


def run_task(client, hosts, task, log_directory, name=None, force=False):
    '''Run a single task on all the specified hosts.'''

    name = name or task['name']
    logging.info("%s: Starting task run", name)

    start_time = time.time()

    # Run the commands asynchronously on all hosts.
    cmd = task['commands']

    includes = ensure_list(task.get('include'))
    for include in reversed(includes):
        with open(include) as f:
            cmd = f.read() + '\n' + cmd

    if force:
        cmd = 'force=yes\n' + cmd

    shell = task.get('shell')
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


def safe_filename(filename):
    # If you want to escape more characters, switch to using re.sub()
    return filename.replace('/', '_')


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

        failed_hosts = [t.host for t in result_dict.values()
                        if t.exit_code != 0]

        if failed_hosts:
            msg = "Task %s failed on: %s" % (
                name, ', '.join(failed_hosts))
            logging.error(msg)
            break

        number += 1
    return all_results


def duration_as_string(seconds):
    m, s = divmod(seconds, 60)
    h, m = divmod(m, 60)
    return ("%d:%02d:%02d" % (h, m, s))


def write_report(f, all_results):
    '''Write a report containing task results and durations.'''
    first_line = True
    for task_name, task_results in all_results.items():
        if first_line:
            first_line = False
        else:
            f.write("\n")

        f.write("%s:\n" % task_name)

        for host, result in task_results.items():
            status = "succeeded" if result.exit_code == 0 else "failed"
            duration = duration_as_string(result.duration)
            f.write("  - %s: %s in %s\n" % (host, status, duration))
