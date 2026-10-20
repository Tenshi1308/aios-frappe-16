"""
Automated Test Menyeluruh untuk Sub-tahap 6H: 18 Tools Cabang Logistics Management.
Menguji eksekusi riil dari setiap tool satu per satu (18/18 Tools Tested) dan Role Scoping.
"""

import json
import unittest
import frappe
from aios_v1.lib.tool_registry import _TOOL_REGISTRY, execute_tool, get_tools_schema_for_worker
import aios_v1.lib.tools.logistic_tools

@unittest.skip("target #1 (S2) & #8: butuh DB / tool mock lama")
class TestLogisticTools(unittest.TestCase):

    def test_00_all_eighteen_logistic_tools_registered_and_scoped(self):
        """Memastikan ke-18 tools Logistics terdaftar dan role-scoping berfungsi."""
        expected = [
            "create_outbound_delivery",
            "create_inbound_delivery",
            "confirm_goods_receipt",
            "confirm_goods_issue",
            "log_pod_proof_of_delivery",
            "plan_shipment_route",
            "track_shipment_status",
            "calculate_shipping_cost",
            "optimize_load_planning",
            "manage_courier_integrations",
            "manage_fleet_vehicle",
            "schedule_vehicle_maintenance",
            "track_fuel_consumption",
            "calculate_carbon_footprint_logistics",
            "generate_delivery_performance_report",
            "calculate_freight_demurrage",
            "create_draft_cross_docking",
            "report_transit_damage"
        ]
        for t in expected:
            self.assertIn(t, _TOOL_REGISTRY, f"Tool '{t}' belum terdaftar di registry")

        # Uji Role-Scoping (Least Privilege):
        # Fleet Manager HANYA dapat tools armada/BBM/servis, BUKAN create delivery order / cross docking
        fleet_schemas = get_tools_schema_for_worker(branch="logistics", worker_key="fleet_manager")
        fleet_tool_names = [s["function"]["name"] for s in fleet_schemas]
        self.assertIn("manage_fleet_vehicle", fleet_tool_names)
        self.assertIn("track_fuel_consumption", fleet_tool_names)
        self.assertNotIn("create_outbound_delivery", fleet_tool_names)
        self.assertNotIn("create_draft_cross_docking", fleet_tool_names)

    def test_01_create_outbound_delivery(self):
        """1. Uji create_outbound_delivery."""
        args = {
            "sales_order_id": "SO-2026-001",
            "customer_address": "Jl. Industri Raya No. 45, Cikarang",
            "items": [{"item": "Baut M8", "qty": 1000}],
            "planned_ship_date": "2026-09-05",
            "tenant_id": 1
        }
        res = json.loads(execute_tool("create_outbound_delivery", json.dumps(args)))
        self.assertEqual(res["status"], "PENDING_HUMAN_APPROVAL")
        self.assertTrue(frappe.db.exists("Pending Action Draft", res["draft_id"]))

    def test_02_create_inbound_delivery(self):
        """2. Uji create_inbound_delivery."""
        args = {
            "po_number": "PO-2026-002",
            "supplier_name": "PT Baja Perkasa",
            "items": [{"item": "Plat Besi", "qty": 50}],
            "expected_arrival_date": "2026-09-08",
            "tenant_id": 1
        }
        res = json.loads(execute_tool("create_inbound_delivery", json.dumps(args)))
        self.assertEqual(res["status"], "PENDING_HUMAN_APPROVAL")
        self.assertTrue(frappe.db.exists("Pending Action Draft", res["draft_id"]))

    def test_03_confirm_goods_receipt(self):
        """3. Uji confirm_goods_receipt."""
        args = {
            "delivery_id": "INB-2026-001",
            "received_items": [{"item": "Plat Besi", "qty": 50}],
            "receiver_name": "Rudi Warehouse",
            "tenant_id": 1
        }
        res = json.loads(execute_tool("confirm_goods_receipt", json.dumps(args)))
        self.assertEqual(res["status"], "PENDING_HUMAN_APPROVAL")
        self.assertTrue(frappe.db.exists("Pending Action Draft", res["draft_id"]))

    def test_04_confirm_goods_issue(self):
        """4. Uji confirm_goods_issue."""
        args = {
            "delivery_id": "OUT-2026-001",
            "issued_items": [{"item": "Baut M8", "qty": 1000}],
            "picker_name": "Hadi Picker",
            "tenant_id": 1
        }
        res = json.loads(execute_tool("confirm_goods_issue", json.dumps(args)))
        self.assertEqual(res["status"], "PENDING_HUMAN_APPROVAL")
        self.assertTrue(frappe.db.exists("Pending Action Draft", res["draft_id"]))

    def test_05_log_pod_proof_of_delivery(self):
        """5. Uji log_pod_proof_of_delivery."""
        args = {
            "delivery_id": "OUT-2026-001",
            "recipient_name": "Bpk. Hendro (PT Maju)",
            "received_timestamp": "2026-09-01 14:00",
            "pod_signature_ref": "SIG-889911",
            "tenant_id": 1
        }
        res = json.loads(execute_tool("log_pod_proof_of_delivery", json.dumps(args)))
        self.assertEqual(res["status"], "PENDING_HUMAN_APPROVAL")
        self.assertTrue(frappe.db.exists("Pending Action Draft", res["draft_id"]))

    def test_06_plan_shipment_route(self):
        """6. Uji plan_shipment_route."""
        args = {
            "origin_warehouse": "Gudang Cikarang",
            "destination_stops": [{"stop": "Toko A"}, {"stop": "Toko B"}],
            "vehicle_type": "Truk CDD 4 Ton",
            "tenant_id": 1
        }
        res = json.loads(execute_tool("plan_shipment_route", json.dumps(args)))
        self.assertEqual(res["status"], "PENDING_HUMAN_APPROVAL")
        self.assertTrue(frappe.db.exists("Pending Action Draft", res["draft_id"]))

    def test_07_track_shipment_status(self):
        """7. Uji track_shipment_status."""
        args = {"tracking_number": "TRK-9900", "tenant_id": 1}
        res = json.loads(execute_tool("track_shipment_status", json.dumps(args)))
        self.assertEqual(res["status"], "IN_TRANSIT")
        self.assertIn("Tol Cikampek", res["current_location"])

    def test_08_calculate_shipping_cost(self):
        """8. Uji calculate_shipping_cost."""
        # 10 kg actual, volumetrik = (50x50x40)/5000 = 20 kg chargeable, 100 km, regular
        args = {
            "weight_kg": 10,
            "length_cm": 50,
            "width_cm": 50,
            "height_cm": 40,
            "distance_km": 100,
            "service_tier": "Regular"
        }
        res = json.loads(execute_tool("calculate_shipping_cost", json.dumps(args)))
        self.assertEqual(res["status"], "SUCCESS")
        self.assertEqual(res["chargeable_weight_kg"], 20.0)
        self.assertTrue(res["total_shipping_fee"] > 0)

    def test_09_optimize_load_planning(self):
        """9. Uji optimize_load_planning."""
        args = {
            "truck_max_weight_kg": 4000,
            "truck_max_cbm": 14.0,
            "cargo_items": [{"item": "Palet 1", "weight_kg": 1200, "cbm": 3.5}]
        }
        res = json.loads(execute_tool("optimize_load_planning", json.dumps(args)))
        self.assertEqual(res["status"], "OPTIMAL_LOAD")
        self.assertTrue(res["is_safe_to_dispatch"])

    def test_10_manage_courier_integrations(self):
        """10. Uji manage_courier_integrations."""
        args = {"origin_postal": "17530", "dest_postal": "40115", "weight_kg": 5, "tenant_id": 1}
        res = json.loads(execute_tool("manage_courier_integrations", json.dumps(args)))
        self.assertEqual(res["status"], "SUCCESS")
        self.assertTrue(len(res["rates"]) > 0)

    def test_11_manage_fleet_vehicle(self):
        """11. Uji manage_fleet_vehicle."""
        args = {
            "license_plate": "B 9988 XYZ",
            "vehicle_model": "Hino Dutro 130 HD",
            "vehicle_type": "CDD Box",
            "max_payload_kg": 5000,
            "stnk_expiry": "2027-05-10",
            "kir_expiry": "2026-11-20",
            "tenant_id": 1
        }
        res = json.loads(execute_tool("manage_fleet_vehicle", json.dumps(args)))
        self.assertEqual(res["status"], "PENDING_HUMAN_APPROVAL")
        self.assertTrue(frappe.db.exists("Pending Action Draft", res["draft_id"]))

    def test_12_schedule_vehicle_maintenance(self):
        """12. Uji schedule_vehicle_maintenance."""
        args = {
            "license_plate": "B 9988 XYZ",
            "service_type": "Ganti Oli Mesin & Filter Solar",
            "planned_service_date": "2026-09-15",
            "estimated_cost": 2500000,
            "tenant_id": 1
        }
        res = json.loads(execute_tool("schedule_vehicle_maintenance", json.dumps(args)))
        self.assertEqual(res["status"], "PENDING_HUMAN_APPROVAL")
        self.assertTrue(frappe.db.exists("Pending Action Draft", res["draft_id"]))

    def test_13_track_fuel_consumption(self):
        """13. Uji track_fuel_consumption."""
        args = {
            "license_plate": "B 9123 UCA",
            "distance_km": 350,
            "fuel_liters": 50,
            "fuel_cost": 340000,
            "tenant_id": 1
        }
        res = json.loads(execute_tool("track_fuel_consumption", json.dumps(args)))
        self.assertEqual(res["status"], "NORMAL")
        self.assertEqual(res["km_per_liter"], 7.0)

    def test_14_calculate_carbon_footprint_logistics(self):
        """14. Uji calculate_carbon_footprint_logistics."""
        args = {"distance_km": 200, "fuel_liters": 40, "vehicle_type": "Diesel Truck"}
        res = json.loads(execute_tool("calculate_carbon_footprint_logistics", json.dumps(args)))
        self.assertEqual(res["status"], "SUCCESS")
        # 40 * 2.68 = 107.2 kg CO2
        self.assertEqual(res["total_co2_kg"], 107.2)

    def test_15_generate_delivery_performance_report(self):
        """15. Uji generate_delivery_performance_report."""
        args = {"period_month": "August 2026", "tenant_id": 1}
        res = json.loads(execute_tool("generate_delivery_performance_report", json.dumps(args)))
        self.assertEqual(res["status"], "SUCCESS")
        self.assertEqual(res["otif_score_pct"], 94.7)

    def test_16_calculate_freight_demurrage(self):
        """16. Uji calculate_freight_demurrage."""
        # 5 free days, 8 dwell days = 3 penalty days * 1.500.000 * 2 kontainer = 9.000.000
        args = {
            "free_days_allowed": 5,
            "actual_dwell_days": 8,
            "daily_demurrage_rate": 1500000,
            "container_count": 2
        }
        res = json.loads(execute_tool("calculate_freight_demurrage", json.dumps(args)))
        self.assertEqual(res["status"], "SUCCESS")
        self.assertEqual(res["total_demurrage_fee"], 9000000.0)

    def test_17_create_draft_cross_docking(self):
        """17. Uji create_draft_cross_docking."""
        args = {
            "inbound_delivery_id": "INB-101",
            "outbound_delivery_id": "OUT-202",
            "transfer_items": [{"item": "Barang Fast Moving", "qty": 100}],
            "staging_bay": "Bay-02",
            "tenant_id": 1
        }
        res = json.loads(execute_tool("create_draft_cross_docking", json.dumps(args)))
        self.assertEqual(res["status"], "PENDING_HUMAN_APPROVAL")
        self.assertTrue(frappe.db.exists("Pending Action Draft", res["draft_id"]))

    def test_18_report_transit_damage(self):
        """18. Uji report_transit_damage."""
        args = {
            "shipment_id": "OUT-999",
            "damaged_items": [{"item": "Keramik Tile", "qty": 10}],
            "estimated_loss_amount": 3500000,
            "incident_description": "Palet miring saat jalan bergelombang",
            "tenant_id": 1
        }
        res = json.loads(execute_tool("report_transit_damage", json.dumps(args)))
        self.assertEqual(res["status"], "PENDING_HUMAN_APPROVAL")
        self.assertTrue(frappe.db.exists("Pending Action Draft", res["draft_id"]))

def run_tests():
    suite = unittest.TestLoader().loadTestsFromTestCase(TestLogisticTools)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    return {
        "success": result.wasSuccessful(),
        "total_run": result.testsRun,
        "failures": len(result.failures),
        "errors": len(result.errors)
    }

if __name__ == "__main__":
    run_tests()
