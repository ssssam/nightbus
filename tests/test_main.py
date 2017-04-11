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

EXAMPLE_TASKS = '''
- name: print-hello
  commands: echo "hello"
'''

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


def test_main(example_hosts, tmpdir):
    '''Basic test that the core functions work.'''

    tasks = nighttrain.tasks.TaskList(EXAMPLE_TASKS)
    hosts = nighttrain.ssh_config.SSHConfig(example_hosts)

    client = pssh.ParallelSSHClient(hosts, host_config=hosts)

    results = {}
    try:
        results = nighttrain.tasks.run_all_tasks(
            client, hosts, tasks, log_directory=str(tmpdir))
    finally:
        if results:
            report_filename = os.path.join(str(tmpdir), 'report')
            with open(report_filename, 'w') as f:
                nighttrain.tasks.write_report(f, results)

    assert sorted(os.listdir(str(tmpdir))) == [
        '1.print-hello.127.0.0.1.log', '1.print-hello.127.0.0.2.log', 'report'
    ]
