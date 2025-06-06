# Copyright 2016-2025 Blue Marble Analytics LLC.
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

""" """

import os.path


def create_csv_generic(
    filename,
    df,
    overwrite,
):
    """ """
    if not os.path.exists(filename) or overwrite:
        df.to_csv(
            filename,
            mode="w",
            index=False,
        )
    else:
        raise ValueError(
            f"The file {filename} already exists and overwrite has not been "
            "indicated."
        )
