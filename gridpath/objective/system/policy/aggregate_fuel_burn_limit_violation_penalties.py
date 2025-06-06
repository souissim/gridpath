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
This module adds horizon fuel burn limit overage penalty costs to the objective
function.
"""

from pyomo.environ import Expression, NonNegativeReals

from gridpath.auxiliary.dynamic_components import cost_components


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
    :param m: the Pyomo abstract model object we are adding components to
    :param d: the DynamicComponents class object we will get components from

    Here, we aggregate total penalty costs for not meeting the energy-target constraint.
    """

    def total_penalty_costs_min_abs_rule(mod):
        return sum(
            mod.Fuel_Burn_Min_Shortage_Abs_Unit_Expression[ba, bt, h]
            * mod.fuel_burn_min_violation_penalty_per_unit[ba]
            * mod.number_years_represented[mod.period[mod.last_hrz_tmp[bt, h]]]
            * mod.discount_factor[mod.period[mod.last_hrz_tmp[bt, h]]]
            for (
                ba,
                bt,
                h,
            ) in mod.FUEL_BA_BLN_TYPE_HRZS_WITH_FUEL_BURN_MIN_ABS_LIMIT
        )

    m.Total_Horizon_Fuel_Burn_Min_Abs_Penalty_Costs = Expression(
        rule=total_penalty_costs_min_abs_rule
    )

    def total_penalty_costs_max_abs_rule(mod):
        return sum(
            mod.Fuel_Burn_Max_Overage_Abs_Unit_Expression[ba, bt, h]
            * mod.fuel_burn_max_violation_penalty_per_unit[ba]
            * mod.number_years_represented[mod.period[mod.last_hrz_tmp[bt, h]]]
            * mod.discount_factor[mod.period[mod.last_hrz_tmp[bt, h]]]
            for (
                ba,
                bt,
                h,
            ) in mod.FUEL_BA_BLN_TYPE_HRZS_WITH_FUEL_BURN_MAX_ABS_LIMIT
        )

    m.Total_Horizon_Fuel_Burn_Max_Abs_Penalty_Costs = Expression(
        rule=total_penalty_costs_max_abs_rule
    )

    def total_penalty_costs_rel_rule(mod):
        return sum(
            mod.Fuel_Burn_Max_Overage_Rel_Unit_Expression[ba, bt, h]
            * mod.fuel_burn_relative_max_violation_penalty_per_unit[ba]
            * mod.number_years_represented[mod.period[mod.last_hrz_tmp[bt, h]]]
            * mod.discount_factor[mod.period[mod.last_hrz_tmp[bt, h]]]
            for (
                ba,
                bt,
                h,
            ) in mod.FUEL_BA_BLN_TYPE_HRZS_WITH_FUEL_BURN_MAX_REL_LIMIT
        )

    m.Total_Horizon_Fuel_Burn_Max_Rel_Penalty_Costs = Expression(
        rule=total_penalty_costs_rel_rule
    )

    record_dynamic_components(dynamic_components=d)


def record_dynamic_components(dynamic_components):
    """
    :param dynamic_components:

    Add total balance penalty costs to cost components for the absolute and relative
    fuel burn limits.
    """

    getattr(dynamic_components, cost_components).append(
        "Total_Horizon_Fuel_Burn_Min_Abs_Penalty_Costs"
    )

    getattr(dynamic_components, cost_components).append(
        "Total_Horizon_Fuel_Burn_Max_Abs_Penalty_Costs"
    )

    getattr(dynamic_components, cost_components).append(
        "Total_Horizon_Fuel_Burn_Max_Rel_Penalty_Costs"
    )
