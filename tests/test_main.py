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

'''Primary test cases for Night Train automation tool.'''

import pytest

import io
import os
import sys

import nighttrain

# Include parallel-ssh submodule in search path.
# As well as getting us the version of parallel-ssh with our local
# modifications, this allows us to access the embedded_server module that
# Parallel-SSH uses for its automated tests.
package_dir = os.path.dirname(__file__)
embedded_pssh_lib_dir = os.path.join(package_dir, '..', 'parallel-ssh')
sys.path = [package_dir, embedded_pssh_lib_dir] + sys.path
import pssh
from embedded_server import embedded_server

@pytest.fixture
def example_hosts():
    '''Fixture providing two temporary SSH servers

    Returns a string describing the server locations, suitable for the
    nighttrain.ssh_config.SSHConfig() class to parse.

    '''
    server_host_1 = '127.0.0.1'

    server_socket_1 = embedded_server.make_socket(server_host_1)
    server_listen_port_1 = server_socket_1.getsockname()[1]
    server_1 = embedded_server.start_server(server_socket_1)

    server_host_2 = '127.0.0.2'
    server_socket_2 = embedded_server.make_socket(server_host_2)
    server_listen_port_2 = server_socket_2.getsockname()[1]
    server_2 = embedded_server.start_server(server_socket_2)

    hosts = '''
        %s: { port: %s }
        %s: { port: %s }
    ''' % (server_host_1, server_listen_port_1, server_host_2, server_listen_port_2)

    # Now it gets a bit ugly. ParallelSSH doesn't let us override the hostname
    # of a given server. The hostname for both of these is 127.0.0.

    return hosts


def test_success_simple(example_hosts, tmpdir):
    '''Basic test of a task that should succeed.'''
    TASKS = '''
    tasks:
    - name: print-hello
      commands: echo "hello"
    '''

    tasks = nighttrain.tasks.TaskList(TASKS)
    hosts = nighttrain.ssh_config.SSHConfig(example_hosts)

    client = pssh.ParallelSSHClient(hosts, host_config=hosts)

    results = nighttrain.tasks.run_all_tasks(
        client, hosts, tasks, log_directory=str(tmpdir))

    report_buffer = io.StringIO()
    nighttrain.tasks.write_report(report_buffer, results)
    report = report_buffer.getvalue()

    assert sorted(os.listdir(str(tmpdir))) == [
        '1.print-hello.127.0.0.1.log', '1.print-hello.127.0.0.2.log'
    ]

    assert '127.0.0.1: succeeded' in report
    assert '127.0.0.2: succeeded' in report


def test_failure_simple(example_hosts, tmpdir):
    '''Basic test of a task that should fail.'''
    TASKS = '''
    tasks:
    - name: print-hello
      commands: exit 1
    '''

    tasks = nighttrain.tasks.TaskList(TASKS)
    hosts = nighttrain.ssh_config.SSHConfig(example_hosts)

    client = pssh.ParallelSSHClient(hosts, host_config=hosts)

    results = nighttrain.tasks.run_all_tasks(
        client, hosts, tasks, log_directory=str(tmpdir))

    report_buffer = io.StringIO()
    nighttrain.tasks.write_report(report_buffer, results)
    report = report_buffer.getvalue()

    assert sorted(os.listdir(str(tmpdir))) == [
        '1.print-hello.127.0.0.1.log', '1.print-hello.127.0.0.2.log'
    ]

    assert '127.0.0.1: failed' in report
    assert '127.0.0.2: failed' in report
