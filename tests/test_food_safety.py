from flavorlab.food_safety import check_food_safety


def test_missing_context_is_indeterminate_not_safe():
    result = check_food_safety(food_temperature_c=55, elapsed_out_of_control_min=None,
                               ambient_c=25, perishable=True, service_mode="immediate_service")
    assert result.status == "indeterminate"
    assert not result.allows_serving_optimization


def test_hot_holding_uses_independent_sixty_degree_reference():
    ok = check_food_safety(food_temperature_c=60, elapsed_out_of_control_min=200,
                           ambient_c=25, perishable=True, service_mode="hot_holding")
    low = check_food_safety(food_temperature_c=59.9, elapsed_out_of_control_min=10,
                            ambient_c=25, perishable=True, service_mode="hot_holding")
    assert ok.status == "meets_hot_holding_reference"
    assert low.status == "requires_action"


def test_room_limits_are_separate_from_thermal_prediction():
    normal = check_food_safety(food_temperature_c=50, elapsed_out_of_control_min=121,
                               ambient_c=25, perishable=True, service_mode="immediate_service")
    hot = check_food_safety(food_temperature_c=50, elapsed_out_of_control_min=61,
                            ambient_c=33, perishable=True, service_mode="immediate_service")
    assert normal.status == hot.status == "time_limit_exceeded"
    assert normal.limits["room_limit_min"] == 120
    assert hot.limits["hot_room_limit_min"] == 60


def test_within_time_reference_is_not_named_safe():
    result = check_food_safety(food_temperature_c=55, elapsed_out_of_control_min=20,
                               ambient_c=25, perishable=True, service_mode="immediate_service")
    assert result.status == "within_time_reference"
    assert "safe" not in result.status
