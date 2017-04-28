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


'''Utility functions.'''


import itertools


def ensure_list(string_or_list_or_none, separator=None):
    if isinstance(string_or_list_or_none, str):
        if separator:
            return string_or_list_or_none.split(separator)
        else:
            return [string_or_list_or_none]
    elif string_or_list_or_none is not None:
        if separator:
            return list(itertools.chain.from_iterable(
                item.split(separator) for item in string_or_list_or_none))
        else:
            return string_or_list_or_none
    else:
        return []
