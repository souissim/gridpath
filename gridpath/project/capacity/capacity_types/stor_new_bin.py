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
This capacity type describes new storage projects that can be built by the
optimization at a pre-specified size, duration and cost. The model can
decide to build the project at the specified size in some or all investment
*periods*, or not at all. Once built, the capacity remains operational and fixed O&M
costs are incurred for the duration of the project's pre-specified operational lifetime.

The capital cost input to the model is an annualized cost per unit of power capacity
(MW) and an annualized cost per unit energy capacity (MWh). The costs are additive.
If the optimization makes the decision to build new power/energy capacity, the total
annualized cost is incurred in each period of the study (and multiplied by the number
of years the period represents) for the duration of the project's financial lifetime.

.. note:: Please note that to calculate the duration of the storage project, i.e.,
    how long it can sustain discharging at its maximum output, you must adjust the
    energy capacity by the discharge efficiency. For example, a 1 MW  with 1 MWh energy
    capacity battery with discharging losses of 5% (discharging_loss_factor = 95%) would
    have a duration of 1 MWh / (1 MW/0.95) or 0.95 hours rather than 1 hour.
"""


import csv
import os.path
from pathlib import Path

import pandas as pd
from pyomo.environ import Set, Param, Var, NonNegativeReals, Constraint, value, Binary

from gridpath.auxiliary.auxiliary import cursor_to_df
from gridpath.auxiliary.dynamic_components import (
    capacity_type_operational_period_sets,
    capacity_type_financial_period_sets,
)
from gridpath.auxiliary.validations import (
    write_validation_to_database,
    get_expected_dtypes,
    get_projects,
    validate_dtypes,
    validate_values,
    validate_idxs,
)
from gridpath.common_functions import create_results_df
from gridpath.project.capacity.capacity_types.common_methods import (
    relevant_periods_by_project_vintage,
    project_relevant_periods,
    project_vintages_relevant_in_period,
    read_results_file_generic,
    write_summary_results_generic,
    get_units,
)


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
    The following Pyomo model components are defined in this module:

    +-------------------------------------------------------------------------+
    | Sets                                                                    |
    +=========================================================================+
    | | :code:`STOR_NEW_BIN`                                                  |
    |                                                                         |
    | The list of projects of capacity type :code:`stor_new_bin`.             |
    +-------------------------------------------------------------------------+
    | | :code:`STOR_NEW_BIN_VNTS`                                             |
    |                                                                         |
    | A two-dimensional set of project-vintage combinations to describe the   |
    | periods in time when storage capacity/energy can be built in the        |
    | optimization.                                                           |
    +-------------------------------------------------------------------------+

    |

    +-------------------------------------------------------------------------+
    | Required Input Params                                                   |
    +=========================================================================+
    | | :code:`stor_new_bin_operational_lifetime_yrs`                         |
    | | *Defined over*: :code:`STOR_NEW_BIN_VNTS`                             |
    | | *Within*: :code:`NonNegativeReals`                                    |
    |                                                                         |
    | The project's lifetime, i.e. how long project capacity/energy of a      |
    | particular vintage remains operational.                                 |
    +-------------------------------------------------------------------------+
    | | :code:`stor_new_bin_fixed_cost_per_mw_yr`                             |
    | | *Defined over*: :code:`STOR_NEW_BIN_VNTS`                             |
    | | *Within*: :code:`NonNegativeReals`                                    |
    |                                                                         |
    | The project's power capacity fixed O&M cost incurred in each year in    |
    | which the project is operational.                                       |
    +-------------------------------------------------------------------------+
    | | :code:`stor_new_bin_fixed_cost_per_stor_mwh_yr`                       |
    | | *Defined over*: :code:`STOR_NEW_BIN_VNTS`                             |
    | | *Within*: :code:`NonNegativeReals`                                    |
    |                                                                         |
    | The project's energy capacity fixed O&M cost incurred in each year in   |
    | which the project is operational.                                       |
    +-------------------------------------------------------------------------+
    | | :code:`stor_new_bin_financial_lifetime_yrs_by_vintage`                |
    | | *Defined over*: :code:`STOR_NEW_BIN_VNTS`                             |
    | | *Within*: :code:`NonNegativeReals`                                    |
    |                                                                         |
    | The project's financial lifetime, i.e. how long project capacity of a   |
    | particular vintage incurs annualized capital costs.                     |
    +-------------------------------------------------------------------------+
    | | :code:`stor_new_bin_annualized_real_cost_per_mw_yr`                   |
    | | *Defined over*: :code:`STOR_NEW_BIN_VNTS`                             |
    | | *Within*: :code:`NonNegativeReals`                                    |
    |                                                                         |
    | The project's cost to build new power capacity in annualized real       |
    | dollars in per MW.                                                      |
    +-------------------------------------------------------------------------+
    | | :code:`stor_new_bin_annualized_real_cost_per_stor_mwh_yr`             |
    | | *Defined over*: :code:`STOR_NEW_BIN_VNTS`                             |
    | | *Within*: :code:`NonNegativeReals`                                    |
    |                                                                         |
    | The project's cost to build new energy capacity in annualized real      |
    | dollars in per MW.                                                      |
    +-------------------------------------------------------------------------+
    | | :code:`stor_new_bin_build_size_mw`                                    |
    | | *Defined over*: :code:`STOR_NEW_BIN`                                  |
    | | *Within*: :code:`NonNegativeReals`                                    |
    |                                                                         |
    | The project's specified power capacity build size in MW. The model can  |
    | only build the project in this pre-specified size.                      |
    +-------------------------------------------------------------------------+
    | | :code:`stor_new_bin_build_size_mwh`                                   |
    | | *Defined over*: :code:`STOR_NEW_BIN`                                  |
    | | *Within*: :code:`NonNegativeReals`                                    |
    |                                                                         |
    | The project's specified energy capacity build size in MWh. The model    |
    | can only build the project in this pre-specified size.                  |
    +-------------------------------------------------------------------------+

    .. note:: The cost input to the model is an annualized cost per unit
        capacity. This annualized cost is incurred in each period of the study
        (and multiplied by the number of years the period represents) for
        the duration of the project's "financial" lifetime. It is up to the
        user to ensure that the variousl lifetime and cost parameters are consistent
        with one another and with the period length (projects are operational
        and incur capital costs only if the operational and financial lifetimes last
        through the end of a period respectively.

    +-------------------------------------------------------------------------+
    | Derived Sets                                                            |
    +=========================================================================+
    | | :code:`OPR_PRDS_BY_STOR_NEW_BIN_VINTAGE`                              |
    | | *Defined over*: :code:`STOR_NEW_BIN_VNTS`                             |
    |                                                                         |
    | Indexed set that describes the operational periods for each possible    |
    | project-vintage combination, based on the                               |
    | :code:`stor_new_bin_operational_lifetime_yrs`. For instance, capacity   |
    | of 2020 vintage with lifetime of 30 years will be assumed operational   |
    | starting Jan 1, 2020 and through Dec 31, 2049, but will *not* be        |
    | operational in 2050.                                                    |
    +-------------------------------------------------------------------------+
    | | :code:`STOR_NEW_BIN_OPR_PRDS`                                         |
    |                                                                         |
    | Two-dimensional set that includes the periods when project capacity of  |
    | any vintage *could* be operational if built. This set is added to the   |
    | list of sets to join to get the final :code:`PRJ_OPR_PRDS` set defined  |
    | in **gridpath.project.capacity.capacity**.                              |
    +-------------------------------------------------------------------------+
    | | :code:`STOR_NEW_BIN_VNTS_OPR_IN_PRD`                                  |
    | | *Defined over*: :code:`PERIODS`                                       |
    |                                                                         |
    | Indexed set that describes the project-vintages that could be           |
    | operational in each period based on the                                 |
    | :code:`stor_new_bin_operational_lifetime_yrs`.                          |
    +-------------------------------------------------------------------------+
    | | :code:`FIN_PRDS_BY_STOR_NEW_BIN_VINTAGE`                              |
    | | *Defined over*: :code:`STOR_NEW_BIN_VNTS`                             |
    |                                                                         |
    | Indexed set that describes the financial periods for each possible      |
    | project-vintage combination, based on the                               |
    | :code:`gen_new_lin_financial_lifetime_yrs_by_vintage`. For instance,    |
    | capacity of  the 2020 vintage with lifetime of 30 years will be assumed |
    | to incur costs starting Jan 1, 2020 and through Dec 31, 2049, but will  |
    | *not* be operational in 2050.                                           |
    +-------------------------------------------------------------------------+
    | | :code:`STOR_NEW_BIN_FIN_PRDS`                                         |
    |                                                                         |
    | Two-dimensional set that includes the periods when project capacity of  |
    | any vintage *could* be incurring costs if built. This set is added to   |
    | the list of sets to join to get the final :code:`PRJ_FIN_PRDS` set      |
    | defined in **gridpath.project.capacity.capacity**.                      |
    +-------------------------------------------------------------------------+

    |

    +-------------------------------------------------------------------------+
    | Variables                                                               |
    +=========================================================================+
    | | :code:`StorNewBin_Build`                                              |
    | | *Defined over*: :code:`STOR_NEW_BIN_VNTS`                             |
    | | *Within*: :code:`Binary`                                              |
    |                                                                         |
    | Binary build decision for each project-vintage combination (1=build).   |
    +-------------------------------------------------------------------------+

    |

    +-------------------------------------------------------------------------+
    | Constraints                                                             |
    +=========================================================================+
    | | :code:`StorNewBin_Only_Build_Once_Constraint`                         |
    | | *Defined over*: :code:`STOR_NEW_BIN_OPR_PRDS`                         |
    |                                                                         |
    | Once a project is built, it cannot be built again in another vintage    |
    | until its lifetime is expired.                                          |
    +-------------------------------------------------------------------------+

    """

    # Sets
    ###########################################################################

    m.STOR_NEW_BIN = Set()

    m.STOR_NEW_BIN_VNTS = Set(dimen=2, within=m.STOR_NEW_BIN * m.PERIODS)

    # Required Params
    ###########################################################################

    m.stor_new_bin_operational_lifetime_yrs = Param(
        m.STOR_NEW_BIN_VNTS, within=NonNegativeReals
    )

    m.stor_new_bin_fixed_cost_per_mw_yr = Param(
        m.STOR_NEW_BIN_VNTS, within=NonNegativeReals
    )

    m.stor_new_bin_fixed_cost_per_stor_mwh_yr = Param(
        m.STOR_NEW_BIN_VNTS, within=NonNegativeReals
    )

    m.stor_new_bin_financial_lifetime_yrs_by_vintage = Param(
        m.STOR_NEW_BIN_VNTS, within=NonNegativeReals
    )

    m.stor_new_bin_annualized_real_cost_per_mw_yr = Param(
        m.STOR_NEW_BIN_VNTS, within=NonNegativeReals
    )

    m.stor_new_bin_annualized_real_cost_per_stor_mwh_yr = Param(
        m.STOR_NEW_BIN_VNTS, within=NonNegativeReals
    )

    m.stor_new_bin_build_size_mw = Param(m.STOR_NEW_BIN, within=NonNegativeReals)

    m.stor_new_bin_build_size_mwh = Param(m.STOR_NEW_BIN, within=NonNegativeReals)

    # Derived Sets
    ###########################################################################

    m.OPR_PRDS_BY_STOR_NEW_BIN_VINTAGE = Set(
        m.STOR_NEW_BIN_VNTS, initialize=operational_periods_by_storage_vintage
    )

    m.STOR_NEW_BIN_OPR_PRDS = Set(dimen=2, initialize=stor_new_bin_operational_periods)

    m.STOR_NEW_BIN_VNTS_OPR_IN_PRD = Set(
        m.PERIODS, dimen=2, initialize=stor_new_bin_vintages_operational_in_period
    )

    m.FIN_PRDS_BY_STOR_NEW_BIN_VINTAGE = Set(
        m.STOR_NEW_BIN_VNTS, initialize=financial_periods_by_storage_vintage
    )

    m.STOR_NEW_BIN_FIN_PRDS = Set(dimen=2, initialize=stor_new_bin_financial_periods)

    m.STOR_NEW_BIN_VNTS_FIN_IN_PRD = Set(
        m.PERIODS, dimen=2, initialize=stor_new_bin_vintages_financial_in_period
    )

    # Variables
    ###########################################################################

    m.StorNewBin_Build = Var(m.STOR_NEW_BIN_VNTS, within=Binary)

    # Constraints
    ###########################################################################

    m.StorNewBin_Only_Build_Once_Constraint = Constraint(
        m.STOR_NEW_BIN_OPR_PRDS, rule=only_build_once_rule
    )

    # Dynamic Components
    ###########################################################################

    # Add to list of sets we'll join to get the final
    # PRJ_OPR_PRDS set
    getattr(d, capacity_type_operational_period_sets).append(
        "STOR_NEW_BIN_OPR_PRDS",
    )

    # Add to list of sets we'll join to get the final
    # PRJ_FIN_PRDS set
    getattr(d, capacity_type_financial_period_sets).append(
        "STOR_NEW_BIN_FIN_PRDS",
    )


# Set Rules
###############################################################################


def operational_periods_by_storage_vintage(mod, prj, v):
    return relevant_periods_by_project_vintage(
        periods=getattr(mod, "PERIODS"),
        period_start_year=getattr(mod, "period_start_year"),
        period_end_year=getattr(mod, "period_end_year"),
        vintage=v,
        lifetime_yrs=mod.stor_new_bin_operational_lifetime_yrs[prj, v],
    )


def stor_new_bin_operational_periods(mod):
    return project_relevant_periods(
        project_vintages_set=mod.STOR_NEW_BIN_VNTS,
        relevant_periods_by_project_vintage_set=mod.OPR_PRDS_BY_STOR_NEW_BIN_VINTAGE,
    )


def stor_new_bin_vintages_operational_in_period(mod, p):
    return project_vintages_relevant_in_period(
        project_vintage_set=mod.STOR_NEW_BIN_VNTS,
        relevant_periods_by_project_vintage_set=mod.OPR_PRDS_BY_STOR_NEW_BIN_VINTAGE,
        period=p,
    )


def financial_periods_by_storage_vintage(mod, prj, v):
    return relevant_periods_by_project_vintage(
        periods=getattr(mod, "PERIODS"),
        period_start_year=getattr(mod, "period_start_year"),
        period_end_year=getattr(mod, "period_end_year"),
        vintage=v,
        lifetime_yrs=mod.stor_new_bin_financial_lifetime_yrs_by_vintage[prj, v],
    )


def stor_new_bin_financial_periods(mod):
    return project_relevant_periods(
        project_vintages_set=mod.STOR_NEW_BIN_VNTS,
        relevant_periods_by_project_vintage_set=mod.FIN_PRDS_BY_STOR_NEW_BIN_VINTAGE,
    )


def stor_new_bin_vintages_financial_in_period(mod, p):
    return project_vintages_relevant_in_period(
        project_vintage_set=mod.STOR_NEW_BIN_VNTS,
        relevant_periods_by_project_vintage_set=mod.FIN_PRDS_BY_STOR_NEW_BIN_VINTAGE,
        period=p,
    )


# Constraint Formulation Rules
###############################################################################


def only_build_once_rule(mod, g, p):
    """
    **Constraint Name**: StorNewBin_Only_Build_Once_Constraint
    **Enforced Over**: STOR_NEW_BIN_OPR_PRDS

    Once a project is built, it cannot be built again in another vintage
    until its lifetime is expired. Said differently, in each period only
    one vintage can have a non-zero binary build decision.

    Note: this constraint could be generalized into a min and max build
    constraint if we want to allow multiple units to be built.
    """
    # Sum of all binary build decisions of vintages operational in the
    # current period should be less than or equal to 1
    return (
        sum(
            mod.StorNewBin_Build[g, v]
            for (gen, v) in mod.STOR_NEW_BIN_VNTS_OPR_IN_PRD[p]
            if gen == g
        )
        <= 1
    )


# Capacity Type Methods
###############################################################################


def capacity_rule(mod, g, p):
    """
    The power capacity of a new storage project in a given operational
    period is equal to the sum of all binary build decisions of vintages
    operational in that period multiplied with the power capacity size.

    Note: only one vintage can have a non-zero StorNewBin_Build variable in
    each period due to the *only_build_once_rule*.
    """
    return sum(
        mod.StorNewBin_Build[g, v] * mod.stor_new_bin_build_size_mw[g]
        for (gen, v) in mod.STOR_NEW_BIN_VNTS_OPR_IN_PRD[p]
        if gen == g
    )


def energy_stor_capacity_rule(mod, g, p):
    """
    The energy capacity of a new storage project in a given operational
    period is equal to the sum of all binary build decisions of vintages
    operational in that period multiplied with the energy capacity size.

    Note: only one vintage can have a non-zero StorNewBin_Build variable in
    each period due to the *only_build_once_rule*.
    """
    return sum(
        mod.StorNewBin_Build[g, v] * mod.stor_new_bin_build_size_mwh[g]
        for (gen, v) in mod.STOR_NEW_BIN_VNTS_OPR_IN_PRD[p]
        if gen == g
    )


def capacity_cost_rule(mod, g, p):
    """
    The capital cost for new storage projects in a given period is the
    capacity-build of a particular vintage times the annualized power cost for
    that vintage plus the energy-build of the same vintages times the
    annualized energy cost for that vintage, summed over all vintages
    incurring costs in the period. Note that power and energy costs are additive.
    """

    return sum(
        mod.StorNewBin_Build[g, v]
        * (
            mod.stor_new_bin_build_size_mw[g]
            * mod.stor_new_bin_annualized_real_cost_per_mw_yr[g, v]
            + mod.stor_new_bin_build_size_mwh[g]
            * mod.stor_new_bin_annualized_real_cost_per_stor_mwh_yr[g, v]
        )
        for (gen, v) in mod.STOR_NEW_BIN_VNTS_FIN_IN_PRD[p]
        if gen == g
    )


def fixed_cost_rule(mod, g, p):
    """
    The fixed O&M cost for new storage projects in a given period is the
    capacity-build of a particular vintage times the fixed power cost for
    that vintage plus the energy-build of the same vintages times the
    annualized energy cost for that vintage, summed over all vintages
    operational in the period. Note that power and energy costs are additive.
    """

    return sum(
        mod.StorNewBin_Build[g, v]
        * (
            mod.stor_new_bin_build_size_mw[g]
            * mod.stor_new_bin_fixed_cost_per_mw_yr[g, v]
            + mod.stor_new_bin_build_size_mwh[g]
            * mod.stor_new_bin_fixed_cost_per_stor_mwh_yr[g, v]
        )
        for (gen, v) in mod.STOR_NEW_BIN_VNTS_OPR_IN_PRD[p]
        if gen == g
    )


def new_capacity_rule(mod, g, p):
    """
    New capacity built at project g in period p.
    Returns 0 if we can't build capacity at this project in period p.
    """
    return (
        mod.StorNewBin_Build[g, p] * mod.stor_new_bin_build_size_mw[g]
        if (g, p) in mod.STOR_NEW_BIN_VNTS
        else 0
    )


def new_energy_stor_capacity_rule(mod, g, p):
    """
    New capacity built at project g in period p.
    Returns 0 if we can't build capacity at this project in period p.
    """
    return (
        mod.StorNewBin_Build[g, p] * mod.stor_new_bin_build_size_mwh[g]
        if (g, p) in mod.STOR_NEW_BIN_VNTS
        else 0
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
    :param data_portal:
    :param scenario_directory:
    :param subproblem:
    :param stage:
    :return:
    """

    # TODO: once we align param names and column names, we will have conflict
    #   because binary storage and generator use same build size param name
    #   in the columns.
    data_portal.load(
        filename=os.path.join(
            scenario_directory,
            weather_iteration,
            hydro_iteration,
            availability_iteration,
            subproblem,
            stage,
            "inputs",
            "new_binary_build_storage_vintage_costs.tab",
        ),
        index=m.STOR_NEW_BIN_VNTS,
        select=(
            "project",
            "vintage",
            "operational_lifetime_yrs",
            "fixed_cost_per_mw_yr",
            "fixed_cost_per_stor_mwh_yr",
            "financial_lifetime_yrs",
            "annualized_real_cost_per_mw_yr",
            "annualized_real_cost_per_stor_mwh_yr",
        ),
        param=(
            m.stor_new_bin_operational_lifetime_yrs,
            m.stor_new_bin_fixed_cost_per_mw_yr,
            m.stor_new_bin_fixed_cost_per_stor_mwh_yr,
            m.stor_new_bin_financial_lifetime_yrs_by_vintage,
            m.stor_new_bin_annualized_real_cost_per_mw_yr,
            m.stor_new_bin_annualized_real_cost_per_stor_mwh_yr,
        ),
    )

    data_portal.load(
        filename=os.path.join(
            scenario_directory,
            weather_iteration,
            hydro_iteration,
            availability_iteration,
            subproblem,
            stage,
            "inputs",
            "new_binary_build_storage_size.tab",
        ),
        index=m.STOR_NEW_BIN,
        select=("project", "binary_build_size_mw", "binary_build_size_mwh"),
        param=(m.stor_new_bin_build_size_mw, m.stor_new_bin_build_size_mwh),
    )


def add_to_project_period_results(
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
    Export new binary build storage results.
    :param scenario_directory:
    :param subproblem:
    :param stage:
    :param m:
    :param d:
    :return:
    """
    results_columns = [
        "new_build_binary",
        "new_build_mw",
        "new_build_stor_mwh",
    ]
    data = [
        [
            prj,
            prd,
            value(m.StorNewBin_Build[prj, prd]),
            value(m.StorNewBin_Build[prj, prd] * m.stor_new_bin_build_size_mw[prj]),
            value(m.StorNewBin_Build[prj, prd] * m.stor_new_bin_build_size_mwh[prj]),
        ]
        for (prj, prd) in m.STOR_NEW_BIN_VNTS
    ]
    captype_df = create_results_df(
        index_columns=["project", "period"],
        results_columns=results_columns,
        data=data,
    )

    return results_columns, captype_df


def summarize_results(
    scenario_directory,
    weather_iteration,
    hydro_iteration,
    availability_iteration,
    subproblem,
    stage,
    summary_results_file,
):
    """
    Summarize new build storage capacity results.
    :param scenario_directory:
    :param subproblem:
    :param stage:
    :param summary_results_file:
    :return:
    """

    # Get the results CSV as dataframe
    capacity_results_agg_df = read_results_file_generic(
        scenario_directory=scenario_directory,
        weather_iteration=weather_iteration,
        hydro_iteration=hydro_iteration,
        availability_iteration=availability_iteration,
        subproblem=subproblem,
        stage=stage,
        capacity_type=Path(__file__).stem,
    )

    # Get all technologies with new build storage power OR energy capacity
    new_build_df = pd.DataFrame(
        capacity_results_agg_df[
            (capacity_results_agg_df["new_build_mw"] > 0)
            | (capacity_results_agg_df["new_build_stor_mwh"] > 0)
        ][["new_build_mw", "new_build_stor_mwh"]]
    )

    # Get the units from the units.csv file
    power_unit, energy_unit, fuel_unit = get_units(scenario_directory)

    # Rename column header
    columns = [
        "New Binary Storage Power Capacity ({})".format(power_unit),
        "New Binary Storage Energy Capacity ({})".format(energy_unit),
    ]

    write_summary_results_generic(
        results_df=new_build_df,
        columns=columns,
        summary_results_file=summary_results_file,
        title="New Binary Storage Capacity",
        empty_title="No new stor_new_bin storage was built.",
    )


# Database
###############################################################################


def get_model_inputs_from_database(
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

    c1 = conn.cursor()
    new_stor_costs = c1.execute(
        """
        SELECT project, vintage, operational_lifetime_yrs,
        fixed_cost_per_mw_yr, fixed_cost_per_stor_mwh_yr, financial_lifetime_yrs,
        annualized_real_cost_per_mw_yr,
        annualized_real_cost_per_stor_mwh_yr
        FROM inputs_project_portfolios
        
        CROSS JOIN
            (SELECT period AS vintage
            FROM inputs_temporal_periods
            WHERE temporal_scenario_id = {}) as relevant_vintages
        
        INNER JOIN
            (SELECT project, vintage, operational_lifetime_yrs, 
            fixed_cost_per_mw_yr, fixed_cost_per_stor_mwh_yr, financial_lifetime_yrs,
            annualized_real_cost_per_mw_yr, annualized_real_cost_per_stor_mwh_yr
            FROM inputs_project_new_cost
            WHERE project_new_cost_scenario_id = {}) as cost
        USING (project, vintage)
        
        WHERE project_portfolio_scenario_id = {}
        AND capacity_type = 'stor_new_bin'
        ;""".format(
            subscenarios.TEMPORAL_SCENARIO_ID,
            subscenarios.PROJECT_NEW_COST_SCENARIO_ID,
            subscenarios.PROJECT_PORTFOLIO_SCENARIO_ID,
        )
    )

    c2 = conn.cursor()
    new_stor_build_size = c2.execute(
        """SELECT project, binary_build_size_mw, binary_build_size_mwh
        FROM inputs_project_portfolios

        INNER JOIN
            (SELECT project, binary_build_size_mw, binary_build_size_mwh
            FROM inputs_project_new_binary_build_size
            WHERE project_new_binary_build_size_scenario_id = {})
        USING (project)

        WHERE project_portfolio_scenario_id = {}
        AND capacity_type = 'stor_new_bin';""".format(
            subscenarios.PROJECT_NEW_BINARY_BUILD_SIZE_SCENARIO_ID,
            subscenarios.PROJECT_PORTFOLIO_SCENARIO_ID,
        )
    )

    return new_stor_costs, new_stor_build_size


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
    new_binary_build_storage_vintage_costs.tab file and the
    new_binary_build_storage_size.tab file
    :param scenario_directory: string, the scenario directory
    :param subscenarios: SubScenarios object with all subscenario info
    :param subproblem:
    :param stage:
    :param conn: database connection
    :return:
    """

    new_stor_costs, new_stor_build_size = get_model_inputs_from_database(
        scenario_id,
        subscenarios,
        weather_iteration,
        hydro_iteration,
        availability_iteration,
        subproblem,
        stage,
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
            "new_binary_build_storage_vintage_costs.tab",
        ),
        "w",
        newline="",
    ) as new_storage_costs_tab_file:
        writer = csv.writer(
            new_storage_costs_tab_file, delimiter="\t", lineterminator="\n"
        )

        # Write header
        writer.writerow(
            [
                "project",
                "vintage",
                "operational_lifetime_yrs",
                "fixed_cost_per_mw_yr",
                "fixed_cost_per_stor_mwh_yr",
                "financial_lifetime_yrs",
                "annualized_real_cost_per_mw_yr",
                "annualized_real_cost_per_stor_mwh_yr",
            ]
        )

        for row in new_stor_costs:
            replace_nulls = ["." if i is None else i for i in row]
            writer.writerow(replace_nulls)

    with open(
        os.path.join(
            scenario_directory,
            weather_iteration,
            hydro_iteration,
            availability_iteration,
            subproblem,
            stage,
            "inputs",
            "new_binary_build_storage_size.tab",
        ),
        "w",
        newline="",
    ) as new_build_size_tab_file:
        writer = csv.writer(
            new_build_size_tab_file, delimiter="\t", lineterminator="\n"
        )

        # Write header
        writer.writerow(["project", "binary_build_size_mw", "binary_build_size_mwh"])

        for row in new_stor_build_size:
            replace_nulls = ["." if i is None else i for i in row]
            writer.writerow(replace_nulls)


# Validation
###############################################################################


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

    # TODO: check that there are no minimum duration inputs for this type
    #   (duration is specified by specifying the build size in mw and mwh)
    #   Maybe also check all other required / not required inputs?
    #   --> see example in gen_must_run operational_type. Seems very verbose and
    #   hard to maintain. Is there a way to generalize this?

    # Get the binary build generator inputs
    new_stor_costs, new_stor_build_size = get_model_inputs_from_database(
        scenario_id,
        subscenarios,
        weather_iteration,
        hydro_iteration,
        availability_iteration,
        subproblem,
        stage,
        conn,
    )

    projects = get_projects(
        conn, scenario_id, subscenarios, "capacity_type", "stor_new_bin"
    )

    # Convert input data into pandas DataFrame
    cost_df = cursor_to_df(new_stor_costs)
    bld_size_df = cursor_to_df(new_stor_build_size)

    # get the project lists
    cost_projects = cost_df["project"].unique()
    bld_size_projects = bld_size_df["project"]

    # Get expected dtypes
    expected_dtypes = get_expected_dtypes(
        conn=conn,
        tables=["inputs_project_new_cost", "inputs_project_new_binary_build_size"],
    )

    # Check dtypes - cost_df
    dtype_errors, error_columns = validate_dtypes(cost_df, expected_dtypes)
    write_validation_to_database(
        conn=conn,
        scenario_id=scenario_id,
        weather_iteration=weather_iteration,
        hydro_iteration=hydro_iteration,
        availability_iteration=availability_iteration,
        subproblem_id=subproblem,
        stage_id=stage,
        gridpath_module=__name__,
        db_table="inputs_project_new_cost",
        severity="High",
        errors=dtype_errors,
    )

    # Check valid numeric columns are non-negative - cost_df
    numeric_columns = [c for c in cost_df.columns if expected_dtypes[c] == "numeric"]
    valid_numeric_columns = set(numeric_columns) - set(error_columns)
    write_validation_to_database(
        conn=conn,
        scenario_id=scenario_id,
        weather_iteration=weather_iteration,
        hydro_iteration=hydro_iteration,
        availability_iteration=availability_iteration,
        subproblem_id=subproblem,
        stage_id=stage,
        gridpath_module=__name__,
        db_table="inputs_project_new_cost",
        severity="High",
        errors=validate_values(cost_df, valid_numeric_columns, min=0),
    )

    # Check dtypes - bld_size_df
    dtype_errors, error_columns = validate_dtypes(bld_size_df, expected_dtypes)
    write_validation_to_database(
        conn=conn,
        scenario_id=scenario_id,
        weather_iteration=weather_iteration,
        hydro_iteration=hydro_iteration,
        availability_iteration=availability_iteration,
        subproblem_id=subproblem,
        stage_id=stage,
        gridpath_module=__name__,
        db_table="inputs_project_new_binary_build_size",
        severity="High",
        errors=dtype_errors,
    )

    # Check valid numeric columns are non-negative - bld_size_df
    numeric_columns = [
        c for c in bld_size_df.columns if expected_dtypes[c] == "numeric"
    ]
    valid_numeric_columns = set(numeric_columns) - set(error_columns)
    write_validation_to_database(
        conn=conn,
        scenario_id=scenario_id,
        weather_iteration=weather_iteration,
        hydro_iteration=hydro_iteration,
        availability_iteration=availability_iteration,
        subproblem_id=subproblem,
        stage_id=stage,
        gridpath_module=__name__,
        db_table="inputs_project_new_binary_build_size",
        severity="High",
        errors=validate_values(bld_size_df, valid_numeric_columns, min=0),
    )

    # Check that all binary new build projects are available in >=1 vintage
    msg = "Expected cost data for at least one vintage."
    write_validation_to_database(
        conn=conn,
        scenario_id=scenario_id,
        weather_iteration=weather_iteration,
        hydro_iteration=hydro_iteration,
        availability_iteration=availability_iteration,
        subproblem_id=subproblem,
        stage_id=stage,
        gridpath_module=__name__,
        db_table="inputs_project_new_cost",
        severity="High",
        errors=validate_idxs(
            actual_idxs=cost_projects, req_idxs=projects, idx_label="project", msg=msg
        ),
    )

    # Check that all binary new build projects have build size specified
    write_validation_to_database(
        conn=conn,
        scenario_id=scenario_id,
        weather_iteration=weather_iteration,
        hydro_iteration=hydro_iteration,
        availability_iteration=availability_iteration,
        subproblem_id=subproblem,
        stage_id=stage,
        gridpath_module=__name__,
        db_table="inputs_project_new_binary_build_size",
        severity="High",
        errors=validate_idxs(
            actual_idxs=bld_size_projects, req_idxs=projects, idx_label="project"
        ),
    )
