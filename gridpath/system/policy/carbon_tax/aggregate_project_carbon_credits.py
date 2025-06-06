# Copyright 2016-2023 Blue Marble Analytics LLC
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
Aggregate carbon credits from the project-period level to the
carbon tax zone - period level.
"""

import os.path
from pyomo.environ import Set, Expression, value

from gridpath.auxiliary.auxiliary import cursor_to_df
from gridpath.auxiliary.db_interface import directories_to_db_values
from gridpath.auxiliary.dynamic_components import carbon_tax_cost_components
from gridpath.common_functions import create_results_df
from gridpath.system.policy.carbon_tax import CARBON_TAX_ZONE_PRD_DF


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
    """ """
    m.CARBON_TAX_ZONES_CARBON_CREDITS_ZONES = Set(
        within=m.CARBON_TAX_ZONES * m.CARBON_CREDITS_ZONES
    )

    def total_carbon_emissions_credits_rule(mod, tax_z, prd):
        """
        Purchased credits for projects in this carbon tax zone.
        We also need to check that we only count credits projects can
        purchase from credits zone that this carbon_tax zone maps to.
        """
        return sum(
            mod.Project_Purchase_Carbon_Credits[prj, z, prd]
            # Projects in this carbon tax zone
            for prj in mod.CARBON_TAX_PRJS_BY_CARBON_TAX_ZONE[tax_z]
            for z in mod.CARBON_CREDITS_ZONES
            if (prj, z, prd)
            in mod.CARBON_CREDITS_PURCHASE_PRJS_CARBON_CREDITS_ZONES_OPR_PRDS
            # Limit to projects in a credit zone mapped to this carbon_tax zone
            if (tax_z, z) in mod.CARBON_TAX_ZONES_CARBON_CREDITS_ZONES
        )

    m.Total_Carbon_Tax_Emissions_Credits = Expression(
        m.CARBON_TAX_ZONE_PERIODS_WITH_CARBON_TAX,
        rule=total_carbon_emissions_credits_rule,
    )

    def credit_cost_reduction(mod, z, prd):
        return -mod.Total_Carbon_Tax_Emissions_Credits[z, prd] * mod.carbon_tax[z, prd]

    m.Total_Carbon_Tax_Credit_Cost_Reduction = Expression(
        m.CARBON_TAX_ZONE_PERIODS_WITH_CARBON_TAX, rule=credit_cost_reduction
    )

    record_dynamic_components(dynamic_components=d)


def record_dynamic_components(dynamic_components):
    """
    :param dynamic_components:

    This method adds project credits to carbon balance
    """

    getattr(dynamic_components, carbon_tax_cost_components).append(
        "Total_Carbon_Tax_Credit_Cost_Reduction"
    )


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
    mapping = c.execute(
        f"""SELECT carbon_tax_zone, carbon_credits_zone
        FROM inputs_system_carbon_tax_zones_carbon_credits_zones
        WHERE carbon_tax_zones_carbon_credits_zones_scenario_id = 
        {subscenarios.CARBON_TAX_ZONES_CARBON_CREDITS_ZONES_SCENARIO_ID}
        AND carbon_tax_zone in (
            SELECT carbon_tax_zone
            FROM inputs_geography_carbon_tax_zones
            WHERE carbon_tax_zone_scenario_id = {subscenarios.CARBON_TAX_ZONE_SCENARIO_ID}
        )
        AND carbon_credits_zone in (
            SELECT carbon_credits_zone
            FROM inputs_geography_carbon_credits_zones
            WHERE carbon_credits_zone_scenario_id = 
            {subscenarios.CARBON_CREDITS_ZONE_SCENARIO_ID}
        )
        ;
        """
    )

    return mapping


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
    (
        db_weather_iteration,
        db_hydro_iteration,
        db_availability_iteration,
        db_subproblem,
        db_stage,
    ) = directories_to_db_values(
        weather_iteration, hydro_iteration, availability_iteration, subproblem, stage
    )

    query_results = get_inputs_from_database(
        scenario_id,
        subscenarios,
        db_weather_iteration,
        db_hydro_iteration,
        db_availability_iteration,
        db_subproblem,
        db_stage,
        conn,
    )
    # carbon_tax_zones_carbon_credits_zone_mapping.tab
    df = cursor_to_df(query_results)
    df = df.fillna(".")
    fpath = os.path.join(
        scenario_directory,
        weather_iteration,
        hydro_iteration,
        availability_iteration,
        subproblem,
        stage,
        "inputs",
        "carbon_tax_zones_carbon_credits_zone_mapping.tab",
    )
    if not df.empty:
        df.to_csv(fpath, index=False, sep="\t")


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

    map_file = os.path.join(
        scenario_directory,
        weather_iteration,
        hydro_iteration,
        availability_iteration,
        subproblem,
        stage,
        "inputs",
        "carbon_tax_zones_carbon_credits_zone_mapping.tab",
    )

    if os.path.exists(map_file):
        data_portal.load(
            filename=map_file,
            set=m.CARBON_TAX_ZONES_CARBON_CREDITS_ZONES,
        )


def export_results(
    scenario_directory,
    weather_iteration,
    hydro_iteration,
    availability_iteration,
    subproblem,
    stage,
    m,
    d,
):
    """

    :param scenario_directory:
    :param subproblem:
    :param stage:
    :param m:
    :param d:
    :return:
    """

    results_columns = [
        "project_credits",
    ]
    data = [
        [z, p, value(m.Total_Carbon_Tax_Emissions_Credits[z, p])]
        for (z, p) in m.CARBON_TAX_ZONE_PERIODS_WITH_CARBON_TAX
    ]
    results_df = create_results_df(
        index_columns=["carbon_tax_zone", "period"],
        results_columns=results_columns,
        data=data,
    )

    for c in results_columns:
        getattr(d, CARBON_TAX_ZONE_PRD_DF)[c] = None
    getattr(d, CARBON_TAX_ZONE_PRD_DF).update(results_df)
