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

import gevent
import yaml

import collections
import itertools
import logging
import os
import time

import nightbus
from nightbus.utils import ensure_list


class Task():
    '''A single task that we can run on one or more hosts.'''
    def __init__(self, attrs, name=None, defaults=None, parameters=None):
        defaults = defaults or {}

        self.name = name or attrs['name']

        includes = ensure_list(defaults.get('include')) + \
                   ensure_list(attrs.get('include'))

        self.script = self._script(
            attrs['commands'], prologue=defaults.get('prologue'),
            includes=includes, parameters=parameters)

        # This gets passed straight to ParallelSSHClient.run_command()
        # so it's no problem for its value to be `None`.
        self.shell = attrs.get('shell', defaults.get('shell'))

    def _script(self, commands, prologue=None, includes=None, parameters=None):
        '''Generate the script that executes this task.'''
        parts = []
        if parameters:
            for name, value in parameters.items():
                parts.append('%s=%s' % (name, value))
        if prologue:
            parts.append(prologue)
        for include in includes:
            with open(include) as f:
                parts.append(f.read())
        parts.append(commands)
        return '\n'.join(parts)


class TaskList(list):
    '''Contains a user-specified list of descriptions of tasks to run.'''
    def __init__(self, text):
        contents = yaml.safe_load(text)

        if isinstance(contents, list):
            defaults = None
            entry_list = contents
        elif isinstance(contents, dict):
            defaults = contents.get('defaults', {})
            entry_list = contents['tasks']
        else:
            raise RuntimeError("Tasks file is invalid.")

        for entry in entry_list:
            self.extend(self._create_tasks(entry, defaults=defaults))

    def _create_tasks(self, entry, defaults=None):
        '''Create one or more task objects for a given task list entry.

        There can be more than one Task object for an entry due to the
        'parameters' option.

        '''
        if 'parameters' in entry:
            tasks = []
            parameters = entry['parameters']

            # Create an iterable for each parameter containing (name, value)
            # pairs, e.g. (('param', 1), ('param', 2), ('param', 3)).
            iterables = []
            for param_name in sorted(parameters.keys()):
                param_values = parameters[param_name]
                param_pairs = list(itertools.product([param_name], param_values))
                iterables.append(param_pairs)

            # From that create a list of every combination of parameter values.
            if len(iterables) > 1:
                combos = list(itertools.product(*iterables))
            else:
                combos = iterables

            # The value of a parameter can be given literally, or given as a
            # dict with 'repr' and 'value' keys. The value used in the task may
            # not be useful when used in the name of the task, it might be an
            # empty string or contain unprintable characters, so you can set
            # the `repr` in these cases to something else.
            def param_repr(value_entry):
                if isinstance(value_entry, dict):
                    return value_entry.get('repr', value_entry['value'])
                else:
                    return str(value_entry)

            def param_value(value_entry):
                if isinstance(value_entry, dict):
                    return value_entry['value']
                else:
                    return value_entry

            # Finally generate the Task object for each parameter combination.
            task_base_name = entry['name']
            for combo in combos:
                this_parameters = {pair[0]: param_value(pair[1]) for pair in combo}
                this_parameter_reprs = [param_repr(pair[1]) for pair in combo]

                this_name = '.'.join([task_base_name] + this_parameter_reprs)
                tasks.append(Task(entry, name=this_name, defaults=defaults,
                                  parameters=this_parameters))
        else:
            tasks = [Task(entry, defaults=defaults)]
        return tasks

    def names(self):
        return [task.name for task in self]


class TaskResult():
    '''Results of executing a one task on one host.'''
    def __init__(self, name, host, duration=None, exit_code=None, message_list=None):
        self.name = name
        self.host = host
        self.duration = duration
        self.exit_code = exit_code
        self.message_list = message_list


def run_task(client, hosts, task, log_directory, run_name=None, force=False):
    '''Run a single task on all the specified hosts.'''

    name = task.name
    run_name = run_name or name
    logging.info("%s: Starting task run", run_name)

    start_time = time.time()

    # Run the commands asynchronously on all hosts.
    cmd = 'task_name=%s\n' % name
    if force:
        cmd += 'force=yes\n'
    cmd += task.script

    shell = task.shell
    output = client.run_command(cmd, shell=shell, stop_on_errors=True)

    # ParallelSSH doesn't give us a way to run a callback when the host
    # produces output or the command completes. In order to stream the
    # output into separate log files, we run a Greenlet to monitor each
    # host.
    def watch_output(output, host):
        log_filename = safe_filename(run_name + '.' + host + '.log')
        log = os.path.join(log_directory, log_filename)

        messages = []
        with open(log, 'wb') as f:
            for line in output[host].stdout:
                f.write(line.encode('unicode-escape'))
                f.write(b'\n')
                if line.startswith('##nightbus '):
                    messages.append(line[len('##nightbus '):])

        duration = time.time() - start_time
        exit_code = output[host].exit_code
        return nightbus.tasks.TaskResult(
            run_name, host, duration=duration, exit_code=exit_code, message_list=messages)

    watchers = [gevent.spawn(watch_output, output, host) for host in hosts]

    gevent.joinall(watchers, raise_error=True)

    logging.info("%s: Started all jobs, waiting for them to finish", run_name)
    client.join(output)
    logging.info("%s: All jobs finished", run_name)

    results = collections.OrderedDict()
    for result in sorted((watcher.value for watcher in watchers),
                         key=lambda result: result.host):
        results[result.host] = result
    return results


def safe_filename(filename):
    # If you want to escape more characters, switch to using re.sub()
    return filename.replace('/', '_')


def run_all_tasks(client, hosts, tasks, log_directory, force=False,
                  ignore_errors=False):
    '''Loop through each task sequentially.

    We only want to run one task on a host at a time, as we assume it'll
    maximize at least one of available CPU, RAM and IO. However, if fast hosts
    could move onto the next task before slow hosts have finished with the
    previous one it might be nice.

    '''
    all_results = collections.OrderedDict()
    number = 1
    for task in tasks:
        name = '%i.%s' % (number, task.name)

        try:
            result_dict = run_task(
                client, hosts, task, log_directory=log_directory,
                run_name=name, force=force)
            all_results[name] = result_dict

            failed_hosts = [t.host for t in result_dict.values()
                            if t.exit_code != 0]

            if failed_hosts:
                msg = "Task %s failed on: %s" % (
                    name, ', '.join(failed_hosts))
                if ignore_errors:
                    logging.warning(msg)
                else:
                    logging.error(msg)
                    break

            number += 1
        except KeyboardInterrupt:
            # If any tasks finished then we should write a report, even if later
            # tasks got interrupted. Thus we must KeyboardInterrupt here so
            # that previous results are returned.
            logging.info("Received KeyboardInterrupt")
            break
    return all_results


def duration_as_string(seconds):
    m, s = divmod(seconds, 60)
    h, m = divmod(m, 60)
    return ("%d:%02d:%02d" % (h, m, s))


def filter_messages_for_task(task_results):
    '''Separate out messages which occured on all hosts.

    Returns a tuple of (global_messages, host_messages):

        global_messages: messages which appeared in the output of every host
        host_messages: a dictionary per host of messages that appeared on that
            host but didn't appear on every host.
    '''
    host_list = list(task_results.keys())
    first_host = host_list[0]

    if len(host_list) == 1:
        message_list = task_results[first_host].message_list
        return message_list, {first_host: message_list}
    else:
        other_hosts = host_list[1:]
        unprocessed_messages = {host: collections.deque(result.message_list)
                                for host, result in task_results.items()}

        global_messages = []
        host_messages = {host:[] for host in host_list}

        # This algorithm isn't smart and will not scale well to lots of
        # messages.

        while unprocessed_messages[first_host]:
            # Take the first message, and search for it in all the other
            # message streams.
            message = unprocessed_messages[first_host].popleft()
            is_global = True
            for host in other_hosts:
                for host_message in unprocessed_messages[host]:
                    if message == host_message:
                        break
                else:
                    is_global = False
                if not is_global:
                    break

            if is_global:
                global_messages.append(message)
                # Now remove this message from the other hosts' message lists,
                # plus anything we find before that (which we take to be host
                # specific messages).
                for host in other_hosts:
                    while len(unprocessed_messages[host]) > 0:
                        host_message = unprocessed_messages[host].popleft()
                        if host_message == message:
                            break
                        host_messages[host].append(host_message)
            else:
                host_messages[first_host].append(message)

        for host in other_hosts:
            host_messages[host] += unprocessed_messages[host]

        return global_messages, host_messages


def write_report(f, all_results):
    '''Write a report containing task results and durations.'''
    first_line = True
    for task_name, task_results in all_results.items():
        if first_line:
            first_line = False
        else:
            f.write("\n")

        f.write("%s:\n" % task_name)

        global_messages, host_messages = filter_messages_for_task(task_results)

        for message in global_messages:
            f.write("  %s\n" % message)

        for host, result in task_results.items():
            status = "succeeded" if result.exit_code == 0 else "failed"
            duration = duration_as_string(result.duration)
            f.write("  - %s: %s in %s\n" % (host, status, duration))
            for message in host_messages[host]:
                f.write("    %s\n" % message)
