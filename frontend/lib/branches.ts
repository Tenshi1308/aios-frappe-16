// Data 9 bidang AIOS — port dari frontend/lib/branches.ts (mockup-v2).
// id = branch key backend (plugin-manager), pekerjaan = job role canonical
// (architecture.md §4). Dipakai peta AI Manager di Home.

export interface Branch {
  id: string;
  icon: string;
  name: string;
  manager: string;
  workers: string[];
}

export const BRANCHES: Branch[] = [
  {
    id: "planning",
    icon: "📊",
    name: "Strategic & Operational Planning",
    manager: "AI Manager Strategic & Operational Planning",
    workers: ["BI Analyst", "Report Developer", "Data Steward"],
  },
  {
    id: "finance",
    icon: "💰",
    name: "Finance",
    manager: "AI Manager Finance",
    workers: ["Finance Staff", "Financial Analyst", "Budgeting Staff", "Treasurer", "CFO"],
  },
  {
    id: "hr",
    icon: "👥",
    name: "Human Resource",
    manager: "AI Manager HR",
    workers: ["HR Staff", "Recruiter", "Payroll Officer", "Training Specialist", "HR Manager"],
  },
  {
    id: "logistics",
    icon: "🚚",
    name: "Logistic Management",
    manager: "AI Manager Logistic Management",
    workers: ["Logistics Coordinator", "Shipping & Receiving Clerk", "Fleet Manager"],
  },
  {
    id: "maintenance",
    icon: "🔧",
    name: "Maintenance Management",
    manager: "AI Manager Maintenance Management",
    workers: ["Maintenance Planner", "Reliability Engineer", "Maintenance Technician"],
  },
  {
    id: "sales",
    icon: "📈",
    name: "Sales and Distribution",
    manager: "AI Manager Sales",
    workers: ["Sales Representative", "Customer Service", "Sales Data Analyst", "Marketing Specialist"],
  },
  {
    id: "quality",
    icon: "✅",
    name: "Quality Management",
    manager: "AI Manager Quality Management",
    workers: ["Quality Inspector", "Quality Engineer", "Quality Auditor", "Quality Control Officer"],
  },
  {
    id: "material",
    icon: "📦",
    name: "Material Management",
    manager: "AI Manager Material Management",
    workers: [
      "Procurement Staff",
      "Senior Procurement Specialist",
      "Purchasing Officer",
      "Inventory Control Manager",
      "Warehouse Inventory Manager",
      "Retail Inventory Manager",
    ],
  },
  {
    id: "manufacturing",
    icon: "🏭",
    name: "Manufacturing",
    manager: "AI Manager Manufacturing",
    workers: ["Production Planner", "Production Scheduler", "Production Supervisor"],
  },
];

export function getBranch(id: string): Branch | undefined {
  return BRANCHES.find((b) => b.id === id);
}

// Warna identitas tiap bidang (pastel-neon) — dipakai peta Home, chat dock,
// dan elemen lain yang perlu aksen warna bidang. Satu sumber biar seragam.
export const BRANCH_GLOW: Record<string, string> = {
  planning: "#7dd3fc", // sky
  finance: "#67e8f9", // cyan
  hr: "#f0abfc", // pink
  logistics: "#fcd34d", // amber
  maintenance: "#fdba74", // peach
  sales: "#a78bfa", // violet
  quality: "#6ee7b7", // mint
  material: "#5eead4", // teal
  manufacturing: "#fda4af", // rose
};
const GLOW_DEFAULT = "#67e8f9";

export function accentOf(id: string) {
  return BRANCH_GLOW[id] || GLOW_DEFAULT;
}

export function rgbaOf(hex: string, a: number) {
  const n = parseInt(hex.slice(1), 16);
  return `rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},${a})`;
}

// Pemetaan Skill SOP canonical untuk masing-masing job role sub-agent
export const WORKER_SKILLS: Record<string, string[]> = {
  // Planning
  "BI Analyst": ["KPI Dashboard", "Cross-Dept Analytics"],
  "Report Developer": ["Scheduled Reports", "Custom Templates"],
  "Data Steward": ["Data Quality Audit", "Data Dictionary"],
  // Finance
  "Finance Staff": ["Expense Anomalies", "Dunning Letters"],
  "Financial Analyst": ["P&L Analysis", "Asset Depreciation", "AR/AP Aging"],
  "Budgeting Staff": ["Budget Allocation", "Pagu Audit"],
  "Treasurer": ["Cashflow 30D", "Bank Reconciliation", "Payment Batch"],
  "CFO": ["Investment & NPV", "Tax Governance"],
  // HR
  "HR Staff": ["Employee Master Data", "Leave Management", "Disciplinary Letters"],
  "Recruiter": ["Talent Screening", "Job Vacancies"],
  "Payroll Officer": ["Batch Payroll", "BPJS Deductions", "Overtime Calc"],
  "Training Specialist": ["Training Programs", "Competency ROI"],
  "HR Manager": ["Workforce Planning", "Performance Appraisal"],
  // Logistics
  "Logistics Coordinator": ["Shipment Tracking", "Route Optimization", "Courier 3PL Sync"],
  "Shipping & Receiving Clerk": ["Outbound Delivery", "Inbound Cargo POD"],
  "Fleet Manager": ["Fleet Maintenance", "Fuel & Carbon Emissions"],
  // Maintenance
  "Maintenance Planner": ["Preventive PM Schedules", "Cost & Backlog Estimator"],
  "Reliability Engineer": ["MTBF/MTTR Reliability", "Predictive PdM Vibration"],
  "Maintenance Technician": ["Breakdown Incident Report", "Sensor Parameter Log"],
  // Sales
  "Sales Representative": ["Customer Quotations", "Credit Limit Check", "Sales Orders"],
  "Customer Service": ["Customer CRM Logs", "Sales Returns & Claims"],
  "Sales Data Analyst": ["Sales Forecasting", "Pareto & Churn Prediction"],
  "Marketing Specialist": ["Lead Routing", "Promo ROI Evaluation"],
  // Quality
  "Quality Inspector": ["AQL Receiving Sampling", "Equipment Calibration"],
  "Quality Engineer": ["SPC Cpk Analysis", "CAPA 8D Tracking"],
  "Quality Auditor": ["ISO 9001 Audits", "Audit Findings Report"],
  "Quality Control Officer": ["CoA Issuance", "Quality Notification NCR"],
  // Material
  "Procurement Staff": ["Purchase Orders", "RFQ & Vendor Comparison"],
  "Senior Procurement Specialist": ["Vendor Rating & Rating", "Consignment Stock"],
  "Purchasing Officer": ["PO Expediting", "Goods Receipt 3-Way Match"],
  "Inventory Control Manager": ["Stock Availability", "ROP & Safety Stock"],
  "Warehouse Inventory Manager": ["Warehouse Space Capacity", "Slow-Moving Aging"],
  "Retail Inventory Manager": ["Stock Adjustment Opname", "Stock Transfer Orders"],
  // Manufacturing
  "Production Planner": ["MRP BOM Explosion", "Work Center Capacity"],
  "Production Scheduler": ["Work Order Sequencing", "Production Rescheduling"],
  "Production Supervisor": ["Output & Scrap Logging", "OEE & Downtime Tracking"],
};

export function getWorkerSkills(roleName: string): string[] {
  return WORKER_SKILLS[roleName] || ["Specialized SOP", "Operational Workflow"];
}

// Pemetaan Tool Python konkret untuk masing-masing Skill SOP
export const SKILL_TOOLS: Record<string, string[]> = {
  // Finance
  "P&L Analysis": ["generate_pnl_statement", "calculate_financial_ratios"],
  "Asset Depreciation": ["calculate_fixed_asset_depreciation", "calculate_multi_tier_tax"],
  "AR/AP Aging": ["get_ar_aging_summary", "get_ap_aging_summary", "flag_anomalous_expenses"],
  "Expense Anomalies": ["flag_anomalous_expenses"],
  "Dunning Letters": ["generate_dunning_letter"],
  "Budget Allocation": ["check_department_budget"],
  "Pagu Audit": ["check_department_budget", "audit_journal_entries"],
  "Cashflow 30D": ["forecast_30d_cashflow", "get_ar_aging_summary"],
  "Bank Reconciliation": ["run_bank_reconciliation"],
  "Payment Batch": ["process_vendor_payment_batch"],
  "Investment & NPV": ["calculate_npv_irr"],
  "Tax Governance": ["calculate_multi_tier_tax", "issue_tax_withholding_slip"],
  // Planning
  "KPI Dashboard": ["generate_kpi_dashboard", "run_trend_analysis"],
  "Cross-Dept Analytics": ["run_cross_department_report"],
  "Scheduled Reports": ["schedule_automated_report"],
  "Custom Templates": ["build_custom_report_template", "compare_actual_vs_budget"],
  "Data Quality Audit": ["analyze_data_quality", "detect_data_anomalies"],
  "Data Dictionary": ["manage_data_dictionary", "analyze_market_share_benchmarks"],
  // HR
  "Employee Master Data": ["create_employee_record", "run_headcount_report"],
  "Leave Management": ["manage_leave_request", "track_attendance_summary"],
  "Disciplinary Letters": ["issue_warning_letter"],
  "Talent Screening": ["screen_applicant_profile"],
  "Job Vacancies": ["post_job_vacancy"],
  "Batch Payroll": ["calculate_payroll_batch", "generate_payslip"],
  "BPJS Deductions": ["calculate_bpjs_contributions"],
  "Overtime Calc": ["calculate_overtime_hours"],
  "Training Programs": ["schedule_training_program"],
  "Competency ROI": ["evaluate_training_effectiveness"],
  "Workforce Planning": ["track_employee_turnover_rate", "calculate_severance_pay"],
  "Performance Appraisal": ["conduct_performance_appraisal", "process_personnel_action"],
  // Logistics
  "Shipment Tracking": ["track_shipment_status", "log_pod_proof_of_delivery"],
  "Route Optimization": ["plan_shipment_route", "calculate_shipping_cost"],
  "Courier 3PL Sync": ["manage_courier_integrations", "create_draft_cross_docking"],
  "Outbound Delivery": ["create_outbound_delivery", "confirm_goods_issue"],
  "Inbound Cargo POD": ["create_inbound_delivery", "confirm_goods_receipt"],
  "Fleet Maintenance": ["manage_fleet_vehicle", "schedule_vehicle_maintenance"],
  "Fuel & Carbon Emissions": ["track_fuel_consumption", "calculate_carbon_footprint_logistics"],
  // Maintenance
  "Preventive PM Schedules": ["schedule_preventive_maintenance", "create_draft_maintenance_order"],
  "Cost & Backlog Estimator": ["estimate_maintenance_cost", "generate_maintenance_backlog"],
  "MTBF/MTTR Reliability": ["calculate_mtbf_mttr", "calculate_overall_equipment_availability"],
  "Predictive PdM Vibration": ["predict_equipment_failure", "run_rcm_analysis"],
  "Breakdown Incident Report": ["create_maintenance_request", "create_draft_loto_procedure"],
  "Sensor Parameter Log": ["log_equipment_reading", "track_spare_parts_usage"],
  // Sales
  "Customer Quotations": ["create_draft_quotation", "calculate_volume_discount"],
  "Credit Limit Check": ["check_customer_credit_limit"],
  "Sales Orders": ["create_draft_sales_order", "create_draft_invoice_from_order"],
  "Customer CRM Logs": ["log_customer_interaction", "check_order_fulfillment_status"],
  "Sales Returns & Claims": ["approve_sales_return"],
  "Sales Forecasting": ["analyze_sales_trends", "generate_sales_forecast"],
  "Pareto & Churn Prediction": ["get_top_pareto_customers", "predict_customer_churn_risk"],
  "Lead Routing": ["match_lead_to_sales_rep"],
  "Promo ROI Evaluation": ["evaluate_promotion_roi", "calculate_customer_lifetime_value"],
  // Quality
  "AQL Receiving Sampling": ["calculate_sampling_size_aql", "create_inspection_lot"],
  "Equipment Calibration": ["verify_calibration_status"],
  "SPC Cpk Analysis": ["run_spc_analysis", "define_inspection_plan"],
  "CAPA 8D Tracking": ["track_corrective_action", "manage_non_conformance"],
  "ISO 9001 Audits": ["schedule_quality_audit", "generate_audit_report"],
  "Audit Findings Report": ["calculate_cost_of_quality"],
  "CoA Issuance": ["issue_certificate_of_analysis", "make_usage_decision"],
  "Quality Notification NCR": ["create_quality_notification", "analyze_defect_trends"],
  // Material
  "Purchase Orders": ["create_draft_purchase_order", "calculate_economic_order_qty"],
  "RFQ & Vendor Comparison": ["create_draft_rfq", "compare_vendor_quotations"],
  "Vendor Rating & Rating": ["evaluate_vendor_performance"],
  "Consignment Stock": ["manage_consignment_stock"],
  "PO Expediting": ["track_purchase_order_status"],
  "Goods Receipt 3-Way Match": ["verify_goods_receipt"],
  "Stock Availability": ["check_stock_availability"],
  "ROP & Safety Stock": ["calculate_reorder_point", "calculate_safety_stock"],
  "Warehouse Space Capacity": ["get_warehouse_capacity_utilization"],
  "Slow-Moving Aging": ["generate_stock_aging_report", "generate_abc_analysis"],
  "Stock Adjustment Opname": ["record_stock_adjustment"],
  "Stock Transfer Orders": ["create_draft_stock_transfer", "audit_stock_reservation"],
  // Manufacturing
  "MRP BOM Explosion": ["explode_bill_of_materials", "check_material_requirements"],
  "Work Center Capacity": ["check_work_center_capacity", "calculate_takt_time"],
  "Work Order Sequencing": ["create_draft_production_order", "generate_production_schedule"],
  "Production Rescheduling": ["reschedule_delayed_orders"],
  "Output & Scrap Logging": ["confirm_production_output", "report_production_scrap"],
  "OEE & Downtime Tracking": ["analyze_oee_metrics", "log_downtime_event"],
};

export function getSkillTools(skillName: string): string[] {
  return SKILL_TOOLS[skillName] || ["execute_business_action"];
}
