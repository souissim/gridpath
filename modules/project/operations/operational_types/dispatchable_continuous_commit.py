#!/usr/bin/env python

"""
Operations of must-run generators. Can't provide reserves.
"""
import os.path
from pandas import read_csv
from pyomo.environ import Var, Set, Param, Constraint, NonNegativeReals, \
    PercentFraction

from modules.auxiliary.auxiliary import generator_subset_init, \
    make_project_time_var_df
from modules.auxiliary.dynamic_components import headroom_variables, \
    footroom_variables


def add_module_specific_components(m, d):
    """
    Add a continuous commit variable to represent the fraction of fleet
    capacity that is on.
    :param m:
    :param d:
    :return:
    """
    # Sets and params
    m.DISPATCHABLE_CONTINUOUS_COMMIT_GENERATORS = Set(
        within=m.PROJECTS,
        initialize=
        generator_subset_init("operational_type",
                              "dispatchable_continuous_commit")
    )

    m.DISPATCHABLE_CONTINUOUS_COMMIT_GENERATOR_OPERATIONAL_TIMEPOINTS = \
        Set(dimen=2,
            rule=lambda mod:
            set((g, tmp) for (g, tmp) in mod.PROJECT_OPERATIONAL_TIMEPOINTS
                if g in mod.DISPATCHABLE_CONTINUOUS_COMMIT_GENERATORS))

    m.disp_cont_commit_min_stable_level_fraction = \
        Param(m.DISPATCHABLE_CONTINUOUS_COMMIT_GENERATORS,
              within=PercentFraction)

    # Variables
    m.Provide_Power_DispContinuousCommit_MW = \
        Var(m.DISPATCHABLE_CONTINUOUS_COMMIT_GENERATOR_OPERATIONAL_TIMEPOINTS,
            within=NonNegativeReals)

    m.Commit_Continuous = \
        Var(m.DISPATCHABLE_CONTINUOUS_COMMIT_GENERATOR_OPERATIONAL_TIMEPOINTS,
            bounds=(0, 1)
            )

    # Operational constraints
    def max_power_rule(mod, g, tmp):
        """
        Power plus upward services cannot exceed capacity.
        :param mod:
        :param g:
        :param tmp:
        :return:
        """
        return mod.Provide_Power_DispContinuousCommit_MW[g, tmp] + \
            sum(getattr(mod, c)[g, tmp]
                for c in getattr(d, headroom_variables)[g]) \
            <= mod.Capacity_MW[g, mod.period[tmp]] * mod.Commit_Continuous[
            g, tmp]
    m.DispContCommit_Max_Power_Constraint = \
        Constraint(
            m.DISPATCHABLE_CONTINUOUS_COMMIT_GENERATOR_OPERATIONAL_TIMEPOINTS,
            rule=max_power_rule
        )

    def min_power_rule(mod, g, tmp):
        """
        Power minus downward services cannot be below a minimum stable level.
        :param mod:
        :param g:
        :param tmp:
        :return:
        """
        return mod.Provide_Power_DispContinuousCommit_MW[g, tmp] - \
            sum(getattr(mod, c)[g, tmp]
                for c in getattr(d, footroom_variables)[g]) \
            >= mod.Commit_Continuous[g, tmp] * mod.Capacity_MW[g, mod.period[tmp]] \
            * mod.disp_cont_commit_min_stable_level_fraction[g]
    m.DispContCommit_Min_Power_Constraint = \
        Constraint(
            m.DISPATCHABLE_CONTINUOUS_COMMIT_GENERATOR_OPERATIONAL_TIMEPOINTS,
            rule=min_power_rule
        )


# ### OPERATIONS ### #
def power_provision_rule(mod, g, tmp):
    """
    Power provision from dispatchable generators is an endogenous variable.
    :param mod:
    :param g:
    :param tmp:
    :return:
    """
    return mod.Provide_Power_DispContinuousCommit_MW[g, tmp]


def commitment_rule(mod, g, tmp):
    return mod.Commit_Continuous[g, tmp]


def curtailment_rule(mod, g, tmp):
    """
    No 'curtailment' -- simply dispatch down
    :param mod:
    :param g:
    :param tmp:
    :return:
    """
    return 0


# ### COSTS ### #
# TODO: figure out how this should work with fleets (unit size here or in data)
def fuel_cost_rule(mod, g, tmp):
    """
    Fuel use in terms of an IO curve with an incremental heat rate above
    the minimum stable level, i.e. a minimum MMBtu input to have the generator
    on plus incremental fuel use for each MWh above the minimum stable level of
    the generator.
    :param mod:
    :param g:
    :param tmp:
    :return:
    """
    return (mod.Commit_Continuous[g, tmp]
    * mod.minimum_input_mmbtu_per_hr[g]
    + (mod.Provide_Power_DispContinuousCommit_MW[g, tmp] -
       (mod.Commit_Continuous[g, tmp] * mod.Capacity_MW[g, mod.period[tmp]]
        * mod.disp_cont_commit_min_stable_level_fraction[g])
       ) * mod.inc_heat_rate_mmbtu_per_mwh[g]
            ) * mod.fuel_price_per_mmbtu[mod.fuel[g]]


def startup_rule(mod, g, tmp):
    """
    Will be positive when there are more generators committed in the current
    timepoint that there were in the previous timepoint.
    If horizon is circular, the last timepoint of the horizon is the
    previous_timepoint for the first timepoint if the horizon;
    if the horizon is linear, no previous_timepoint is defined for the first
    timepoint of the horizon, so return 'None' here
    :param mod:
    :param g:
    :param tmp:
    :return:
    """
    if tmp == mod.first_horizon_timepoint[mod.horizon[tmp]] \
            and mod.boundary[mod.horizon[tmp]] == "linear":
        return None
    else:
        return mod.Commit_Continuous[g, tmp] \
            - mod.Commit_Continuous[g, mod.previous_timepoint[tmp]]


def shutdown_rule(mod, g, tmp):
    """
    Will be positive when there were more generators committed in the previous
    timepoint that there are in the current timepoint.
    If horizon is circular, the last timepoint of the horizon is the
    previous_timepoint for the first timepoint if the horizon;
    if the horizon is linear, no previous_timepoint is defined for the first
    timepoint of the horizon, so return 'None' here
    :param mod:
    :param g:
    :param tmp:
    :return:
    """
    if tmp == mod.first_horizon_timepoint[mod.horizon[tmp]] \
            and mod.boundary[mod.horizon[tmp]] == "linear":
        return None
    else:
        return mod.Commit_Continuous[g, mod.previous_timepoint[tmp]] \
            - mod.Commit_Continuous[g, tmp]


def fix_commitment(mod, g, tmp):
    """

    :param mod:
    :param g:
    :param tmp:
    :return:
    """
    mod.Commit_Continuous[g, tmp] = mod.fixed_commitment[g, tmp]
    mod.Commit_Continuous[g, tmp].fixed = True


def load_module_specific_data(mod, data_portal, scenario_directory,
                              horizon, stage):
    """

    :param mod:
    :param data_portal:
    :param scenario_directory:
    :param horizon:
    :param stage:
    :return:
    """
    min_stable_fraction = dict()
    dynamic_components = \
        read_csv(
            os.path.join(scenario_directory, "inputs", "projects.tab"),
            sep="\t", usecols=["project", "operational_type",
                               "min_stable_level_fraction"]
            )
    for row in zip(dynamic_components["project"],
                   dynamic_components["operational_type"],
                   dynamic_components["min_stable_level_fraction"]):
        if row[1] == "dispatchable_continuous_commit":
            min_stable_fraction[row[0]] = float(row[2])
        else:
            pass

    data_portal.data()["disp_cont_commit_min_stable_level_fraction"] = \
        min_stable_fraction


def export_module_specific_results(mod, d):
    """
    Export commitment decisions.
    :param mod:
    :param d:
    :return:
    """

    continuous_commit_df = \
        make_project_time_var_df(
            mod,
            "DISPATCHABLE_CONTINUOUS_COMMIT_GENERATOR_OPERATIONAL_TIMEPOINTS",
            "Commit_Continuous",
            ["project", "timepoint"],
            "commit_continuous"
        )

    d.module_specific_df.append(continuous_commit_df)