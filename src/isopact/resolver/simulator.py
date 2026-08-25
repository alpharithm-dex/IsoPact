from __future__ import annotations

from typing import Any

from isopact.simulator.services import CarrierService, CrmService, JiraService, WarehouseService

from .engine import AmbiguousCompensationOutcome, AuthoritativeCompensationFailure


class SimulatorCompensationPort:
    def __init__(self, *, carrier: CarrierService, warehouse: WarehouseService, jira: JiraService, crm: CrmService) -> None:
        self.carrier, self.warehouse, self.jira, self.crm = carrier, warehouse, jira, crm
        self.call_counts: dict[str, int] = {}
        self.lose_response_for: set[str] = set()
        self.fail_authoritatively_for: set[str] = set()

    def get_state(self, target_system: str, target_id: str) -> str:
        if target_system == "carrier": return str(self.carrier.get_shipment(target_id)["state"])
        if target_system == "warehouse": return str(self.warehouse.get_reservation(target_id)["state"])
        if target_system == "jira": return str(self.jira.get_ticket(target_id)["status"])
        if target_system == "crm": return str(self.crm.get_credit(target_id)["state"])
        raise ValueError(f"unsupported compensation target {target_system}")

    def execute(self, action_type: str, target_id: str) -> dict[str, Any]:
        self.call_counts[action_type] = self.call_counts.get(action_type, 0) + 1
        if action_type in self.fail_authoritatively_for: raise AuthoritativeCompensationFailure(action_type)
        if action_type == "carrier.cancel_label": output = self.carrier.cancel(target_id)
        elif action_type == "warehouse.release_stock": output = self.warehouse.release(target_id)
        elif action_type == "jira.reopen_ticket": output = self.jira.reopen_ticket(target_id, "isopact-resolver", "Required settlement evidence is absent")
        elif action_type == "crm.reverse_credit": output = self.crm.reverse(target_id)
        else: raise ValueError(f"unregistered external action {action_type}")
        if action_type in self.lose_response_for: raise AmbiguousCompensationOutcome(action_type)
        return dict(output)
