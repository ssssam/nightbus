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

'''Test cases for Night Bus task descriptions.'''

import nightbus

import os
import tempfile


def test_simple():
    '''Basic test of task list parser.'''

    tasklist = nightbus.tasks.TaskList('''
    tasks:
    - name: print-hello
      commands: echo "hello"
    ''')

    assert tasklist.names() == ['print-hello']


def test_no_tasks_header():
    '''The task list is allowed to just be a list.'''

    tasklist = nightbus.tasks.TaskList('''
    - name: print-hello
      commands: echo "hello"
    ''')

    assert tasklist.names() == ['print-hello']


def test_defaults():
    '''Set attributes that apply to all tasks in the task list.'''

    tasks = '''
    defaults:
      shell: bash -l -c
      prologue: set -e
    tasks:
      - name: print-hello
        commands: echo "hello"
      - name: say-goodbye
        commands: echo "goodbye"
    '''

    tasklist = nightbus.tasks.TaskList(tasks)

    assert tasklist[0].shell == 'bash -l -c'
    assert tasklist[0].script == 'set -e\necho "hello"'
    assert tasklist[1].shell == 'bash -l -c'
    assert tasklist[1].script == 'set -e\necho "goodbye"'


def test_include(tmpdir):
    '''Include one or more files before the task itself.'''

    tasks_template = '''
    defaults:
      include: %s
    tasks:
    - name: print-hello
      include: %s
      commands: echo "hello"
    - name: print-hello-2
      include: [ %s, %s ]
      commands: echo "hello"
    '''

    def temporary_file(text):
        f = tempfile.NamedTemporaryFile(dir=str(tmpdir), mode='w')
        f.write(text)
        f.seek(0)
        return f

    include_1 = temporary_file('set -e')
    include_2 = temporary_file('echo "I am included"')
    include_3 = temporary_file('echo "I am also included"')

    tasks = tasks_template % (include_1.name, include_2.name, include_2.name,
                              include_3.name)

    tasklist = nightbus.tasks.TaskList(tasks)

    assert tasklist[0].script == 'set -e\necho "I am included"\necho "hello"'
    assert tasklist[1].script == \
        'set -e\necho "I am included"\necho "I am also included"\necho "hello"'
