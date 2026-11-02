"""Checagens conservadoras de manutenção e exposição térmica.

Os estados descrevem conformidade com referências gerais, nunca uma declaração
universal de que o alimento está seguro.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field


HOT_HOLDING_MIN_C = 60.0
ROOM_LIMIT_MIN = 120.0
HOT_ROOM_LIMIT_MIN = 60.0
HOT_ROOM_THRESHOLD_C = 32.0


@dataclass
class SafetyAssessment:
    status: str
    allows_serving_optimization: bool
    reasons: list[str]
    limits: dict
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def check_food_safety(
    *, food_temperature_c: float | None, elapsed_out_of_control_min: float | None,
    ambient_c: float | None, perishable: bool | None, service_mode: str,
) -> SafetyAssessment:
    limits = {
        "hot_holding_min_c": HOT_HOLDING_MIN_C,
        "room_limit_min": ROOM_LIMIT_MIN,
        "hot_room_limit_min": HOT_ROOM_LIMIT_MIN,
        "hot_room_threshold_c": HOT_ROOM_THRESHOLD_C,
        "reference": "USDA FSIS; verificar normas brasileiras e regras específicas do alimento",
    }
    if perishable is None:
        return SafetyAssessment("indeterminate", False, ["perecibilidade não informada"], limits)
    if not perishable:
        return SafetyAssessment("not_applicable", True, ["marcado como não perecível"], limits)
    if food_temperature_c is None or ambient_c is None:
        return SafetyAssessment("indeterminate", False, ["temperaturas necessárias não informadas"], limits)
    if service_mode == "hot_holding":
        if food_temperature_c >= HOT_HOLDING_MIN_C:
            return SafetyAssessment("meets_hot_holding_reference", True,
                                    ["temperatura atende à referência geral de manutenção quente"], limits)
        return SafetyAssessment("requires_action", False,
                                ["temperatura abaixo da referência de manutenção quente"], limits,
                                ["não usar degustação como justificativa para manutenção morna prolongada"])
    if service_mode != "immediate_service":
        return SafetyAssessment("indeterminate", False,
                                ["modo exige regra específica de cocção, resfriamento ou armazenamento"], limits)
    if elapsed_out_of_control_min is None:
        return SafetyAssessment("indeterminate", False,
                                ["tempo fora de controle térmico não informado"], limits)
    limit = HOT_ROOM_LIMIT_MIN if ambient_c > HOT_ROOM_THRESHOLD_C else ROOM_LIMIT_MIN
    if elapsed_out_of_control_min > limit:
        return SafetyAssessment("time_limit_exceeded", False,
                                [f"tempo informado excede a referência geral de {limit:.0f} min"], limits)
    return SafetyAssessment(
        "within_time_reference", True,
        [f"serviço imediato dentro da referência temporal geral de {limit:.0f} min"], limits,
        ["isto não confirma cocção, manipulação ou armazenamento seguros"],
    )
