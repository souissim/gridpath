#!/usr/bin/env python

from collections import OrderedDict
from importlib import import_module
import os.path
import sys
import unittest

from tests.common_functions import create_abstract_model, \
    add_components_and_load_data

TEST_DATA_DIRECTORY = \
    os.path.join(os.path.dirname(__file__), "..", "..", "test_data")

# Import prerequisite modules
PREREQUISITE_MODULE_NAMES = []
NAME_OF_MODULE_BEING_TESTED = "project.operations.fuels"
IMPORTED_PREREQ_MODULES = list()
for mdl in PREREQUISITE_MODULE_NAMES:
    try:
        imported_module = import_module("." + str(mdl), package="modules")
        IMPORTED_PREREQ_MODULES.append(imported_module)
    except ImportError:
        print("ERROR! Module " + str(mdl) + " not found.")
        sys.exit(1)
# Import the module we'll test
try:
    MODULE_BEING_TESTED = import_module("." + NAME_OF_MODULE_BEING_TESTED,
                                        package="modules")
except ImportError:
    print("ERROR! Couldn't import module " + NAME_OF_MODULE_BEING_TESTED +
          " to test.")


class TestOperationalCosts(unittest.TestCase):
    """

    """
    def test_add_model_components(self):
        """
        Test that there are no errors when adding model components
        :return:
        """
        create_abstract_model(prereq_modules=IMPORTED_PREREQ_MODULES,
                              module_to_test=MODULE_BEING_TESTED,
                              test_data_dir=TEST_DATA_DIRECTORY,
                              horizon="",
                              stage=""
                              )

    def test_load_model_data(self):
        """
        Test that data are loaded with no errors
        :return:
        """
        add_components_and_load_data(prereq_modules=IMPORTED_PREREQ_MODULES,
                                     module_to_test=MODULE_BEING_TESTED,
                                     test_data_dir=TEST_DATA_DIRECTORY,
                                     horizon="",
                                     stage=""
                                     )

    def test_data_loaded_correctly(self):
        """
        Test that the data loaded are as expected
        :return:
        """
        m, data = add_components_and_load_data(
            prereq_modules=IMPORTED_PREREQ_MODULES,
            module_to_test=MODULE_BEING_TESTED,
            test_data_dir=TEST_DATA_DIRECTORY,
            horizon="",
            stage=""
        )
        instance = m.create_instance(data)

        # Set: FUELS
        expected_fuels = sorted(["Uranium", "Coal", "Gas"])
        actual_fuels = sorted([fuel for fuel in instance.FUELS])
        self.assertListEqual(expected_fuels, actual_fuels)

        # Param: fuel_price_per_mmbtu
        expected_price = OrderedDict(sorted(
            {"Uranium": 2, "Coal": 4, "Gas": 5}.items()
                                            )
                                     )
        actual_price = OrderedDict(sorted(
            {f: instance.fuel_price_per_mmbtu[f]
             for f in instance.FUELS}.items()
                                            )
                                     )
        self.assertDictEqual(expected_price, actual_price)

        # Param: co2_intensity_tons_per_mmbtu
        expected_co2 = OrderedDict(sorted(
            {"Uranium": 0, "Coal": 0.09552, "Gas": 0.05306}.items()
                                            )
                                     )
        actual_co2 = OrderedDict(sorted(
            {f: instance.co2_intensity_tons_per_mmbtu[f]
             for f in instance.FUELS}.items()
                                            )
                                     )
        self.assertDictEqual(expected_co2, actual_co2)