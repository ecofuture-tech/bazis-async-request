# Copyright 2026 EcoFuture Technology Services LLC and contributors
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


def normalize(data):
    """
    Removes the parts of a stored or returned response that depend on the versions of the
    middleware and on DEBUG: the content length, the Vary header, the code and the
    traceback of errors.
    """
    if isinstance(data, dict):
        result = {}
        for key, value in data.items():
            if key in ('traceback', 'code') and 'detail' in data:
                continue
            if key == 'headers' and isinstance(value, list):
                value = [
                    list(it) for it in value if str(it[0]).lower() not in ('content-length', 'vary')
                ]
            result[key] = normalize(value)
        return result
    if isinstance(data, list):
        return [normalize(it) for it in data]
    return data
