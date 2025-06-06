# Copyright 2022 (c) Crown Copyright, GC.
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


from collections import OrderedDict
from importlib import import_module
import os.path
import sys
import unittest

from tests.common_functions import create_abstract_model, add_components_and_load_data

TEST_DATA_DIRECTORY = os.path.join(
    os.path.dirname(__file__), "..", "..", "..", "test_data"
)

# Import prerequisite modules
PREREQUISITE_MODULE_NAMES = [
    "temporal.operations.timepoints",
    "temporal.investment.periods",
    "temporal.operations.horizons",
    "geography.performance_standard_zones",
]
NAME_OF_MODULE_BEING_TESTED = "system.policy.performance_standard.performance_standard"
IMPORTED_PREREQ_MODULES = list()
for mdl in PREREQUISITE_MODULE_NAMES:
    try:
        imported_module = import_module("." + str(mdl), package="gridpath")
        IMPORTED_PREREQ_MODULES.append(imported_module)
    except ImportError:
        print("ERROR! Module " + str(mdl) + " not found.")
        sys.exit(1)
# Import the module we'll test
try:
    MODULE_BEING_TESTED = import_module(
        "." + NAME_OF_MODULE_BEING_TESTED, package="gridpath"
    )
except ImportError:
    print("ERROR! Couldn't import module " + NAME_OF_MODULE_BEING_TESTED + " to test.")


class TestPerformanceStandard(unittest.TestCase):
    """ """

    def test_add_model_components(self):
        """
        Test that there are no errors when adding model components
        :return:
        """
        create_abstract_model(
            prereq_modules=IMPORTED_PREREQ_MODULES,
            module_to_test=MODULE_BEING_TESTED,
            test_data_dir=TEST_DATA_DIRECTORY,
            weather_iteration="",
            hydro_iteration="",
            availability_iteration="",
            subproblem="",
            stage="",
        )

    def test_load_model_data(self):
        """
        Test that data are loaded with no errors
        :return:
        """
        add_components_and_load_data(
            prereq_modules=IMPORTED_PREREQ_MODULES,
            module_to_test=MODULE_BEING_TESTED,
            test_data_dir=TEST_DATA_DIRECTORY,
            weather_iteration="",
            hydro_iteration="",
            availability_iteration="",
            subproblem="",
            stage="",
        )

    def test_data_loaded_correctly(self):
        """
        Test components initialized with data as expected
        :return:
        """
        m, data = add_components_and_load_data(
            prereq_modules=IMPORTED_PREREQ_MODULES,
            module_to_test=MODULE_BEING_TESTED,
            test_data_dir=TEST_DATA_DIRECTORY,
            weather_iteration="",
            hydro_iteration="",
            availability_iteration="",
            subproblem="",
            stage="",
        )
        instance = m.create_instance(data)

        # Set: PERFORMANCE_STANDARD_ZONE_PERIODS_WITH_PERFORMANCE_STANDARD
        expected_ps_zone_periods = sorted(
            [
                ("PS_Zone1", 2020),
                ("PS_Zone1", 2030),
                ("PS_Zone2", 2020),
                ("PS_Zone2", 2030),
            ]
        )
        actual_ps_zone_periods = sorted(
            [
                (z, p)
                for (
                    z,
                    p,
                ) in instance.PERFORMANCE_STANDARD_ZONE_PERIODS_WITH_PERFORMANCE_STANDARD
            ]
        )
        self.assertListEqual(expected_ps_zone_periods, actual_ps_zone_periods)

        # Param: performance_standard_tco2_per_mwh
        expected_ps = OrderedDict(
            sorted(
                {
                    ("PS_Zone1", 2020): 0.1,
                    ("PS_Zone1", 2030): 0.1,
                    ("PS_Zone2", 2020): 0.1,
                    ("PS_Zone2", 2030): 0.1,
                }.items()
            )
        )
        actual_ps = OrderedDict(
            sorted(
                {
                    (z, p): instance.performance_standard_tco2_per_mwh[z, p]
                    for (
                        z,
                        p,
                    ) in instance.PERFORMANCE_STANDARD_ZONE_PERIODS_WITH_PERFORMANCE_STANDARD
                }.items()
            )
        )
        self.assertDictEqual(expected_ps, actual_ps)

        # Param: performance_standard_tco2_per_mw
        expected_ps_mw = OrderedDict(
            sorted(
                {
                    ("PS_Zone1", 2020): 876,
                    ("PS_Zone1", 2030): 876,
                    ("PS_Zone2", 2020): 876,
                    ("PS_Zone2", 2030): 876,
                }.items()
            )
        )
        actual_ps_mw = OrderedDict(
            sorted(
                {
                    (z, p): instance.performance_standard_tco2_per_mw[z, p]
                    for (
                        z,
                        p,
                    ) in instance.PERFORMANCE_STANDARD_ZONE_PERIODS_WITH_PERFORMANCE_STANDARD
                }.items()
            )
        )
        self.assertDictEqual(expected_ps_mw, actual_ps_mw)


if __name__ == "__main__":
    unittest.main()
