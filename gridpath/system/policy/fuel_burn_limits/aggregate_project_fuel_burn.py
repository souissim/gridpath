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
Aggregate fuel burn from the project-timepoint level to fuel / fuel balancing area -
period level.
"""

import csv
import os.path
from pyomo.environ import Param, Set, Expression
import pandas as pd
from gridpath.auxiliary.db_interface import directories_to_db_values
from gridpath.auxiliary.dynamic_components import fuel_burn_balance_components


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
    m.PRJ_FUEL_BURN_LIMIT_BAS = Set(dimen=2)

    m.FUEL_FUEL_BURN_LIMIT_BAS = Set(dimen=2)

    m.PRJ_FUELS_WITH_LIMITS = Set(
        dimen=2,
        within=m.PROJECTS * m.FUELS,
        initialize=lambda mod: [
            (prj, f)
            for (prj, ba) in mod.PRJ_FUEL_BURN_LIMIT_BAS
            for (f, _ba) in mod.FUEL_FUEL_BURN_LIMIT_BAS
            if _ba == ba and (prj, f) in mod.FUEL_PRJ_FUELS
        ],
    )

    m.FUEL_PRJS_FUEL_WITH_LIMITS_OPR_TMPS = Set(
        dimen=3,
        initialize=lambda mod: [
            (prj, f, tmp)
            for (prj, f, tmp) in mod.FUEL_PRJS_FUEL_OPR_TMPS
            if (prj, f) in mod.PRJ_FUELS_WITH_LIMITS
        ],
    )

    m.PRJS_BY_FUEL_BA = Set(
        m.FUEL_BURN_LIMIT_BAS,
        within=m.FUEL_PRJS,
        initialize=lambda mod, ba: [
            prj for (prj, bln_a) in mod.PRJ_FUEL_BURN_LIMIT_BAS if ba == bln_a
        ],
    )

    m.FUELS_BY_FUEL_BA = Set(
        m.FUEL_BURN_LIMIT_BAS,
        within=m.FUELS,
        initialize=lambda mod, ba: [
            f for (f, bln_a) in mod.FUEL_FUEL_BURN_LIMIT_BAS if ba == bln_a
        ],
    )

    def total_period_fuel_burn_by_fuel_burn_limit_ba_rule(mod, ba, bt, h):
        """
        Calculate total fuel burn from all projects in a fuel balancing area.

        :param mod:
        :param z:
        :param p:
        :return:
        """
        return sum(
            (
                mod.Total_Fuel_Burn_by_Fuel_MMBtu[prj, fuel, tmp]
                - mod.Project_Fuel_Contribution_by_Fuel[prj, fuel, tmp]
            )
            * mod.hrs_in_tmp[tmp]
            * mod.tmp_weight[tmp]
            for (prj, fuel, tmp) in mod.FUEL_PRJS_FUEL_WITH_LIMITS_OPR_TMPS
            if prj in mod.PRJS_BY_FUEL_BA[ba]  # find projects for this BA
            if fuel in mod.FUELS_BY_FUEL_BA[ba]  # find fuel for this BA
            and tmp in mod.TMPS_BY_BLN_TYPE_HRZ[bt, h]  # only tmps in relevant horizon
        )

    m.Total_Horizon_Fuel_Burn_By_Fuel_BA_Unit = Expression(
        m.FUEL_BA_BLN_TYPE_HRZS_WITH_FUEL_BURN_LIMIT,
        rule=total_period_fuel_burn_by_fuel_burn_limit_ba_rule,
    )

    record_dynamic_components(dynamic_components=d)


def record_dynamic_components(dynamic_components):
    """
    :param dynamic_components:

    This method adds project emissions to carbon balance
    """

    getattr(dynamic_components, fuel_burn_balance_components).append(
        "Total_Horizon_Fuel_Burn_By_Fuel_BA_Unit"
    )


# Input-Output
###############################################################################


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
    project_list = list()
    fuel_list = list()

    _df = pd.read_csv(
        os.path.join(
            scenario_directory,
            weather_iteration,
            hydro_iteration,
            availability_iteration,
            subproblem,
            stage,
            "inputs",
            "project_and_fuels_fuel_burn_limit_bas.tab",
        ),
        sep="\t",
        usecols=[
            "project",
            "fuel",
            "fuel_burn_limit_ba",
        ],
    )
    for r in zip(
        _df["project"],
        _df["fuel"],
        _df["fuel_burn_limit_ba"],
    ):
        project_list.append((r[0], r[2]))
        fuel_list.append((r[1], r[2]))

    project_list_no_dupl = list(dict.fromkeys(project_list))
    fuel_list_no_dupl = list(dict.fromkeys(fuel_list))

    data_portal.data()["PRJ_FUEL_BURN_LIMIT_BAS"] = {None: project_list_no_dupl}
    data_portal.data()["FUEL_FUEL_BURN_LIMIT_BAS"] = {None: fuel_list_no_dupl}


# Database
###############################################################################


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

    c = conn.cursor()

    # TODO: do we need additional filtering
    project_fuel_bas = c.execute(
        """SELECT project, fuel, fuel_burn_limit_ba
        FROM
        -- Get projects from portfolio only
        (SELECT project
            FROM inputs_project_portfolios
            WHERE project_portfolio_scenario_id = {project_portfolio_scenario_id}
        ) as prj_tbl
        LEFT OUTER JOIN 
        -- Get BAs for those projects
        (SELECT project, fuel_burn_limit_ba
            FROM inputs_project_fuel_burn_limit_balancing_areas
            WHERE project_fuel_burn_limit_ba_scenario_id = {project_fuel_burn_limit_ba_scenario_id}
        ) as prj_fbl_tbl
        USING (project)
        -- Filter out projects whose BA is not one included in 
        -- our fuel_burn_limit_ba_scenario_id
        INNER JOIN (
            SELECT fuel_burn_limit_ba
                FROM inputs_geography_fuel_burn_limit_balancing_areas
                WHERE fuel_burn_limit_ba_scenario_id = {fuel_burn_limit_ba_scenario_id}
        )
        USING (fuel_burn_limit_ba)
        LEFT OUTER JOIN
        (SELECT fuel, fuel_burn_limit_ba
            FROM inputs_fuel_fuel_burn_limit_balancing_areas
            WHERE fuel_fuel_burn_limit_ba_scenario_id = {fuel_fuel_burn_limit_ba_scenario_id}
        ) as fuel_fbl_tbl
        USING (fuel_burn_limit_ba)
        INNER JOIN (
            SELECT DISTINCT fuel
                FROM inputs_project_fuels
                WHERE (project, project_fuel_scenario_id) in (
                    SELECT DISTINCT project, project_fuel_scenario_id
                    FROM inputs_project_operational_chars
                    WHERE project_operational_chars_scenario_id = {project_operational_chars_scenario_id}
                    AND project in (
                    SELECT DISTINCT project
                    FROM inputs_project_portfolios
                    WHERE project_portfolio_scenario_id = {project_portfolio_scenario_id}
                    )
                )
        )
        USING (fuel);
        """.format(
            project_portfolio_scenario_id=subscenarios.PROJECT_PORTFOLIO_SCENARIO_ID,
            project_fuel_burn_limit_ba_scenario_id=subscenarios.PROJECT_FUEL_BURN_LIMIT_BA_SCENARIO_ID,
            fuel_burn_limit_ba_scenario_id=subscenarios.FUEL_BURN_LIMIT_BA_SCENARIO_ID,
            fuel_fuel_burn_limit_ba_scenario_id=subscenarios.FUEL_FUEL_BURN_LIMIT_BA_SCENARIO_ID,
            project_operational_chars_scenario_id=subscenarios.PROJECT_OPERATIONAL_CHARS_SCENARIO_ID,
        )
    )

    return project_fuel_bas


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
    projects.tab file (to be precise, amend it).
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

    project_fuel_bas = get_inputs_from_database(
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
            "project_and_fuels_fuel_burn_limit_bas.tab",
        ),
        "w",
        newline="",
    ) as projects_file_out:
        writer = csv.writer(projects_file_out, delimiter="\t", lineterminator="\n")
        # Write header
        writer.writerow(["project", "fuel", "fuel_burn_limit_ba"])

        for row in project_fuel_bas:
            writer.writerow(row)
