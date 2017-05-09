#!/usr/bin/env python
# Copyright 2017 Blue Marble Analytics LLC. All rights reserved.

"""
Aggregate carbon emissions from the project-timepoint level to
the carbon cap zone - period level.
"""

import csv
import os.path
from pyomo.environ import Param, Set, Expression, value

from gridpath.auxiliary.dynamic_components import \
    carbon_cap_balance_emission_components


def add_model_components(m, d):
    """

    :param m:
    :param d:
    :return:
    """
    def total_carbon_emissions_rule(mod, z, p):
        """
        Calculate total emissions from all carbonaceous generators in carbon
        cap zone
        :param mod:
        :param z:
        :param p:
        :return:
        """
        return sum(mod.Carbon_Emissions_Tons[g, tmp]
                   * mod.number_of_hours_in_timepoint[tmp]
                   * mod.horizon_weight[mod.horizon[tmp]]
                   for (g, tmp) in
                   mod.CARBONACEOUS_PROJECT_OPERATIONAL_TIMEPOINTS
                   if g in mod.CARBONACEOUS_PROJECTS_BY_CARBON_CAP_ZONE[z]
                   and tmp in mod.TIMEPOINTS_IN_PERIOD[p]
                   )

    m.Total_Carbon_Emissions_Tons = Expression(
        m.CARBON_CAP_ZONE_PERIODS_WITH_CARBON_CAP,
        rule=total_carbon_emissions_rule
    )

    # Add to emission imports to carbon balance
    getattr(d, carbon_cap_balance_emission_components).append(
        "Total_Carbon_Emissions_Tons"
    )


def export_results(scenario_directory, horizon, stage, m, d):
    """

    :param scenario_directory:
    :param horizon:
    :param stage:
    :param m:
    :param d:
    :return:
    """
    with open(os.path.join(scenario_directory, horizon, stage, "results",
                           "carbon_cap_total_project.csv"), "wb") as \
            rps_results_file:
        writer = csv.writer(rps_results_file)
        writer.writerow(["carbon_cap_zone", "period", "carbon_cap_target_mmt",
                         "project_carbon_emissions_mmt"])
        for (z, p) in m.CARBON_CAP_ZONE_PERIODS_WITH_CARBON_CAP:
            writer.writerow([
                z,
                p,
                float(m.carbon_cap_target_mmt[z, p]),
                value(
                    m.Total_Carbon_Emissions_Tons[z, p]
                ) / 10**6  # MMT
            ])


def import_results_into_database(
        scenario_id, c, db, results_directory
):
    """

    :param scenario_id:
    :param c:
    :param db:
    :param results_directory:
    :return:
    """
    # Carbon emissions by in-zone projects
    print("system carbon emissions (project)")
    c.execute(
        """DELETE FROM results_system_carbon_emissions 
        WHERE scenario_id = {};""".format(
            scenario_id
        )
    )
    db.commit()

    # Create temporary table, which we'll use to sort results and then drop
    c.execute(
        """DROP TABLE IF EXISTS 
        temp_results_system_carbon_emissions"""
        + str(scenario_id) + """;"""
    )
    db.commit()

    c.execute(
        """CREATE TABLE temp_results_system_carbon_emissions"""
        + str(scenario_id) + """(
         scenario_id INTEGER,
         carbon_cap_zone VARCHAR(64),
         period INTEGER,
         carbon_cap_mmt FLOAT,
         in_zone_project_emissions_mmt FLOAT,
         PRIMARY KEY (scenario_id, carbon_cap_zone, period)
         );"""
    )
    db.commit()

    # Load results into the temporary table
    with open(os.path.join(results_directory,
                           "carbon_cap_total_project.csv"), "r") as \
            emissions_file:
        reader = csv.reader(emissions_file)

        reader.next()  # skip header
        for row in reader:
            carbon_cap_zone = row[0]
            period = row[1]
            carbon_cap_mmt = row[2]
            project_carbon_emissions_mmt = row[3]

            c.execute(
                """INSERT INTO 
                temp_results_system_carbon_emissions"""
                + str(scenario_id) + """
                 (scenario_id, carbon_cap_zone, period, carbon_cap_mmt, 
                 in_zone_project_emissions_mmt)
                 VALUES ({}, '{}', {}, {}, {});""".format(
                    scenario_id, carbon_cap_zone, period, carbon_cap_mmt,
                    project_carbon_emissions_mmt
                )
            )
    db.commit()

    # Insert sorted results into permanent results table
    c.execute(
        """INSERT INTO results_system_carbon_emissions
        (scenario_id, carbon_cap_zone, period, carbon_cap_mmt, 
        in_zone_project_emissions_mmt)
        SELECT
        scenario_id, carbon_cap_zone, period, carbon_cap_mmt, 
        in_zone_project_emissions_mmt
        FROM temp_results_system_carbon_emissions"""
        + str(scenario_id)
        + """
         ORDER BY scenario_id, carbon_cap_zone, period;"""
    )
    db.commit()

    # Drop the temporary table
    c.execute(
        """DROP TABLE temp_results_system_carbon_emissions"""
        + str(scenario_id) +
        """;"""
    )
    db.commit()