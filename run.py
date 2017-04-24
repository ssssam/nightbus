#!/usr/bin/python3
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

import os
import runpy
import sys

package_dir = os.path.dirname(__file__)

# Use embedded fork of ParallelSSH.
embedded_pssh_lib_dir = os.path.join(package_dir, 'parallel-ssh')
sys.path = [package_dir, embedded_pssh_lib_dir] + sys.path

runpy.run_module('nightbus')
