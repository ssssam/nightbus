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

import yaml


class TaskList(list):
    '''Contains a user-specified list of descriptions of tasks to run.'''
    def __init__(self, filename):
        with open(filename) as f:
            self.extend(yaml.safe_load(f))

    def names(self):
        return [task['name'] for task in self]


class TaskResult():
    '''Results of executing a one task on one host.'''
    def __init__(self, name, host, duration=None, exit_code=None):
        self.name = name
        self.host = host
        self.duration = duration
        self.exit_code = exit_code
