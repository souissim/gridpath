# Copyright 2016-2023 Blue Marble Analytics LLC.
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
import pandas as pd
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
    "geography.load_zones",
    "geography.load_following_down_balancing_areas",
    "geography.water_network",
    "system.water.water_system_params",
    "system.water.water_nodes",
    "system.water.water_flows",
    "system.water.water_node_inflows_outflows",
    "system.water.reservoirs",
    "system.water.water_node_balance",
    "system.water.powerhouses",
    "system.load_balance.static_load_requirement",
    "project",
    "project.capacity.capacity",
    "project.availability.availability",
    "project.fuels",
    "project.operations",
    "project.capacity.potential",
    "project.operations.reserves.lf_reserves_down",
    "project.operations.operational_types",
    "project.operations.power",
    "system.load_balance.aggregate_load_modifier_power",
]
NAME_OF_MODULE_BEING_TESTED = "system.reserves.requirement.lf_reserves_down"
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


class TestCosts(unittest.TestCase):
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
        Test components initialized with expected data
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

        # Set: LF_RESERVES_DOWN_ZONE_TIMEPOINTS
        req_df = pd.read_csv(
            os.path.join(
                TEST_DATA_DIRECTORY, "inputs", "lf_reserves_down_tmp_requirement.tab"
            ),
            sep="\t",
        )

        expected_ba_tmps = sorted(list(zip(req_df.LOAD_ZONES, req_df.timepoint)))
        actual_ba_tmps = sorted(
            [(z, tmp) for (z, tmp) in instance.LF_RESERVES_DOWN_ZONES * instance.TMPS]
        )
        self.assertListEqual(expected_ba_tmps, actual_ba_tmps)

        # Param: lf_reserves_down_requirement_mw
        expected_req = OrderedDict(
            sorted(
                req_df.set_index(["LOAD_ZONES", "timepoint"])
                .to_dict()["load_mw"]
                .items()
            )
        )
        actual_req = OrderedDict(
            sorted(
                {
                    (z, tmp): instance.lf_reserves_down_requirement_mw[z, tmp]
                    for (z, tmp) in instance.LF_RESERVES_DOWN_ZONES * instance.TMPS
                }.items()
            )
        )
        self.assertDictEqual(expected_req, actual_req)

        # Param: lf_down_per_req
        expected_perc_req = OrderedDict({"Zone1": 0.03, "Zone2": 0})
        actual_perc_req = OrderedDict(
            sorted(
                {
                    z: instance.lf_down_per_req[z]
                    for z in instance.LF_RESERVES_DOWN_ZONES
                }.items()
            )
        )
        self.assertDictEqual(expected_perc_req, actual_perc_req)

        # Set: LF_DOWN_BA_LZ
        expected_ba_lzs = sorted(
            [("Zone1", "Zone1"), ("Zone1", "Zone2"), ("Zone1", "Zone3")]
        )
        actual_ba_lzs = sorted([(ba, lz) for (ba, lz) in instance.LF_DOWN_BA_LZ])
        self.assertListEqual(expected_ba_lzs, actual_ba_lzs)


if __name__ == "__main__":
    unittest.main()
