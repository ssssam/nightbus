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


import pssh.utils
import yaml

import os


class SSHConfig(dict):
    '''Dict holding SSH configuration to access each host'''
    def __init__(self, text):
        self.update(yaml.safe_load(text))

        self._load_private_keys()

    def _load_private_keys(self):
        for host, config in self.items():
            if 'private_key' in config:
                config['private_key'] = pssh.utils.load_private_key(
                    config['private_key'])
            if 'proxy_private_key' in config:
                config['proxy_private_key'] = pssh.utils.load_private_key(
                    config['proxy_private_key'])
