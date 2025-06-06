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

"""
Simplest implementation with a MWh target
"""

import csv
import os.path
from pyomo.environ import Set, Param, NonNegativeReals, PercentFraction, Expression

from gridpath.auxiliary.db_interface import directories_to_db_values


def add_model_components(
    m,
    d,
    scenario_directory,
    weather_iteration,
    hydro_iteration,
    availability_iteration,
    subproblem,
    stage,
):
    """

    :param m:
    :param d:
    :return:
    """

    m.ENERGY_TARGET_ZONE_PERIODS_WITH_ENERGY_TARGET = Set(
        dimen=2, within=m.ENERGY_TARGET_ZONES * m.PERIODS
    )

    # RPS target specified in energy terms
    m.period_energy_target_mwh = Param(
        m.ENERGY_TARGET_ZONE_PERIODS_WITH_ENERGY_TARGET,
        within=NonNegativeReals,
        default=0,
    )

    # RPS target specified in 'percent of load' terms
    m.period_energy_target_fraction = Param(
        m.ENERGY_TARGET_ZONE_PERIODS_WITH_ENERGY_TARGET,
        within=PercentFraction,
        default=0,
    )

    # Load zones included in RPS percentage target
    m.PERIOD_ENERGY_TARGET_ZONE_LOAD_ZONES = Set(
        dimen=2, within=m.ENERGY_TARGET_ZONES * m.LOAD_ZONES
    )

    def energy_target_rule(mod, energy_target_zone, period):
        """
        The RPS target consists of two additive components: an energy term
        and a 'percent of load x load' term, where a mapping between the RPS
        zone and the load zones whose load to consider must be specified.
        Either the energy target or the percent target can be omitted (they
        default to 0). If a mapping is not specified, the
        'percent of load x load' is 0.
        """
        # If we have a map of RPS zones to load zones, apply the percentage
        # target; if no map provided, the percentage_target is 0
        if mod.PERIOD_ENERGY_TARGET_ZONE_LOAD_ZONES:
            total_period_load_modifier_adjusted_load = sum(
                mod.LZ_Modified_Load_in_Tmp[lz, tmp]
                * mod.hrs_in_tmp[tmp]
                * mod.tmp_weight[tmp]
                for (
                    _energy_target_zone,
                    lz,
                ) in mod.PERIOD_ENERGY_TARGET_ZONE_LOAD_ZONES
                if _energy_target_zone == energy_target_zone
                for tmp in mod.TMPS
                if tmp in mod.TMPS_IN_PRD[period]
            )
            percentage_target = (
                mod.period_energy_target_fraction[energy_target_zone, period]
                * total_period_load_modifier_adjusted_load
            )
        else:
            percentage_target = 0

        return (
            mod.period_energy_target_mwh[energy_target_zone, period] + percentage_target
        )

    m.Period_Energy_Target = Expression(
        m.ENERGY_TARGET_ZONE_PERIODS_WITH_ENERGY_TARGET, rule=energy_target_rule
    )


def load_model_data(
    m,
    d,
    data_portal,
    scenario_directory,
    weather_iteration,
    hydro_iteration,
    availability_iteration,
    subproblem,
    stage,
):
    """

    :param m:
    :param d:
    :param data_portal:
    :param scenario_directory:
    :param subproblem:
    :param stage:
    :return:
    """
    # Load the targets
    data_portal.load(
        filename=os.path.join(
            scenario_directory,
            weather_iteration,
            hydro_iteration,
            availability_iteration,
            subproblem,
            stage,
            "inputs",
            "period_energy_targets.tab",
        ),
        index=m.ENERGY_TARGET_ZONE_PERIODS_WITH_ENERGY_TARGET,
        param=(
            m.period_energy_target_mwh,
            m.period_energy_target_fraction,
        ),
    )

    # If we have a RPS zone to load zone map input file, load it; otherwise,
    # initialize PERIOD_ENERGY_TARGET_ZONE_LOAD_ZONES as an empty list
    map_filename = os.path.join(
        scenario_directory,
        weather_iteration,
        hydro_iteration,
        availability_iteration,
        subproblem,
        stage,
        "inputs",
        "period_energy_target_load_zone_map.tab",
    )
    if os.path.exists(map_filename):
        data_portal.load(
            filename=map_filename, set=m.PERIOD_ENERGY_TARGET_ZONE_LOAD_ZONES
        )
    else:
        data_portal.data()["PERIOD_ENERGY_TARGET_ZONE_LOAD_ZONES"] = {None: []}


def get_inputs_from_database(
    scenario_id,
    subscenarios,
    weather_iteration,
    hydro_iteration,
    availability_iteration,
    subproblem,
    stage,
    conn,
):
    """
    :param subscenarios: SubScenarios object with all subscenario info
    :param subproblem:
    :param stage:
    :param conn: database connection
    :return:
    """

    # Get the energy and percent targets
    c = conn.cursor()
    energy_targets = c.execute(
        """SELECT energy_target_zone, period, energy_target_mwh, 
        energy_target_fraction
        FROM inputs_system_period_energy_targets
        JOIN
        (SELECT period
        FROM inputs_temporal_periods
        WHERE temporal_scenario_id = {}) as relevant_periods
        USING (period)
        JOIN
        (SELECT energy_target_zone
        FROM inputs_geography_energy_target_zones
        WHERE energy_target_zone_scenario_id = {}) as relevant_zones
        USING (energy_target_zone)
        WHERE period_energy_target_scenario_id = {}
        AND subproblem_id = {}
        AND stage_ID = {};
        """.format(
            subscenarios.TEMPORAL_SCENARIO_ID,
            subscenarios.ENERGY_TARGET_ZONE_SCENARIO_ID,
            subscenarios.PERIOD_ENERGY_TARGET_SCENARIO_ID,
            subproblem,
            stage,
        )
    )

    # Get any RPS zone to load zone mapping for the percent target
    c2 = conn.cursor()
    lz_mapping = c2.execute(
        """SELECT energy_target_zone, load_zone
        FROM inputs_system_period_energy_target_load_zone_map
        JOIN
        (SELECT energy_target_zone
        FROM inputs_geography_energy_target_zones
        WHERE energy_target_zone_scenario_id = {}) as relevant_zones
        using (energy_target_zone)
        WHERE period_energy_target_scenario_id = {}
        """.format(
            subscenarios.ENERGY_TARGET_ZONE_SCENARIO_ID,
            subscenarios.PERIOD_ENERGY_TARGET_SCENARIO_ID,
        )
    )

    return energy_targets, lz_mapping


def validate_inputs(
    scenario_id,
    subscenarios,
    weather_iteration,
    hydro_iteration,
    availability_iteration,
    subproblem,
    stage,
    conn,
):
    """
    Get inputs from database and validate the inputs
    :param subscenarios: SubScenarios object with all subscenario info
    :param subproblem:
    :param stage:
    :param conn: database connection
    :return:
    """
    # TODO: warn if percentage target is specified but no mapping to load
    #  zones or vice versa
    pass
    # Validation to be added
    # energy_targets = get_inputs_from_database(
    #     scenario_id, subscenarios, subproblem, stage, conn)


def write_model_inputs(
    scenario_directory,
    scenario_id,
    subscenarios,
    weather_iteration,
    hydro_iteration,
    availability_iteration,
    subproblem,
    stage,
    conn,
):
    """
    Get inputs from database and write out the model input
    period_energy_targets.tab file.
    :param scenario_directory: string, the scenario directory
    :param subscenarios: SubScenarios object with all subscenario info
    :param subproblem:
    :param stage:
    :param conn: database connection
    :return:
    """

    (
        db_weather_iteration,
        db_hydro_iteration,
        db_availability_iteration,
        db_subproblem,
        db_stage,
    ) = directories_to_db_values(
        weather_iteration, hydro_iteration, availability_iteration, subproblem, stage
    )

    energy_targets, lz_mapping = get_inputs_from_database(
        scenario_id,
        subscenarios,
        db_weather_iteration,
        db_hydro_iteration,
        db_availability_iteration,
        db_subproblem,
        db_stage,
        conn,
    )

    with open(
        os.path.join(
            scenario_directory,
            weather_iteration,
            hydro_iteration,
            availability_iteration,
            subproblem,
            stage,
            "inputs",
            "period_energy_targets.tab",
        ),
        "w",
        newline="",
    ) as energy_targets_tab_file:
        writer = csv.writer(
            energy_targets_tab_file, delimiter="\t", lineterminator="\n"
        )

        # Write header
        writer.writerow(
            [
                "energy_target_zone",
                "period",
                "energy_target_mwh",
                "energy_target_fraction",
            ]
        )

        for row in energy_targets:
            # It's OK if targets are not specified; they default to 0
            replace_nulls = ["." if i is None else i for i in row]
            writer.writerow(replace_nulls)

    # Write the RPS zone to load zone map file for the RPS percent target if
    # there are any mappings only
    energy_target_lz_map_list = [row for row in lz_mapping]
    if energy_target_lz_map_list:
        with open(
            os.path.join(
                scenario_directory,
                weather_iteration,
                hydro_iteration,
                availability_iteration,
                subproblem,
                stage,
                "inputs",
                "period_energy_target_load_zone_map.tab",
            ),
            "w",
            newline="",
        ) as energy_target_lz_map_tab_file:
            writer = csv.writer(
                energy_target_lz_map_tab_file, delimiter="\t", lineterminator="\n"
            )

            # Write header
            writer.writerow(["energy_target_zone", "load_zone"])
            for row in energy_target_lz_map_list:
                writer.writerow(row)
