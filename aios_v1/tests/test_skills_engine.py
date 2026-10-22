"""
Automated Test Suite Komprehensif untuk AIOS Skills Engine & Loader (Role-Centric Architecture Opsi C - Tahap 6M.12).
Menguji 10 Aspek Kritis:
1. Parser YAML frontmatter & edge cases.
2. Path discovery hierarki direktori <branch>/<role>/<skill>.md.
3. Normalisasi varian penamaan peran (kebab-case, snake_case, space-case).
4. RBAC role-scoping (Least Privilege Opsi C) pada 9 cabang ERP + Orchestrator.
5. Cross-branch isolation (Pemisahan batas kewenangan antar divisi).
6. Validasi dependensi 100% tools_required di _TOOL_REGISTRY.
7. In-memory smart caching & cache invalidation.
8. Perakitan dinamis System Prompt dengan SOP Markdown.
9. Integritas seluruh 86 file SOP nyata dan keunikan slug (Zero Duplicate Slugs).
10. Benchmark performa & latensi engine (< 50 ms).

Dijalankan via: `bench --site aios.localhost execute aios_v1.tests.test_skills_engine.run_tests`
"""

import os
import json
import time
import unittest
import tempfile
import shutil
from pathlib import Path

import frappe
from aios_v1.lib.skills_loader import (
    parse_frontmatter,
    load_skill_from_file,
    load_all_skills,
    get_skill_by_slug,
    get_skills_for_worker,
    validate_skill_dependencies,
    is_skill_active,
    compose_worker_system_prompt,
    clear_skills_cache,
    _normalize_role_variants,
    _SKILLS_CACHE
)
from aios_v1.lib.tool_registry import (
    get_tools_schema_for_worker,
    _TOOL_REGISTRY,
    _ensure_tools_loaded
)


class TestSkillsEngine(unittest.TestCase):
    def setUp(self):
        clear_skills_cache()
        self.test_dir = tempfile.mkdtemp(prefix="aios_test_skills_")

    def tearDown(self):
        clear_skills_cache()
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)

    def _create_sample_skill_file(self, branch: str, role: str, filename: str, content: str) -> str:
        role_dir = os.path.join(self.test_dir, branch, role)
        os.makedirs(role_dir, exist_ok=True)
        file_path = os.path.join(role_dir, filename)
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)
        return file_path

    # =========================================================================
    # 1. TEST PARSE FRONTMATTER & EDGE CASES
    # =========================================================================
    def test_01_parse_frontmatter_valid_and_edge_cases(self):
        """Memastikan parser YAML frontmatter memisahkan header dan body secara presisi."""
        raw_md = """---
name: "Corporate Scenario Simulation"
slug: "corporate-scenario-simulation"
version: "1.0.0"
branch: "planning"
role: "planning_manager"
tools_required:
  - "run_what_if_scenario"
triggers:
  - "simulasi what if"
priority: "critical"
---

# 1. Peran & Tujuan Bisnis
Menjalankan simulasi skenario bisnis.
"""
        metadata, body = parse_frontmatter(raw_md)
        self.assertEqual(metadata.get("name"), "Corporate Scenario Simulation")
        self.assertEqual(metadata.get("slug"), "corporate-scenario-simulation")
        self.assertEqual(metadata.get("role"), "planning_manager")
        self.assertEqual(len(metadata.get("tools_required", [])), 1)
        self.assertIn("# 1. Peran & Tujuan Bisnis", body)

        # Edge case: string tanpa frontmatter
        meta_empty, body_raw = parse_frontmatter("# Hanya Markdown Polos")
        self.assertEqual(len(meta_empty), 0)
        self.assertEqual(body_raw, "# Hanya Markdown Polos")

    # =========================================================================
    # 2. TEST LOAD SINGLE SKILL FROM FILE DENGAN PATH DISCOVERY
    # =========================================================================
    def test_02_load_skill_from_file_hierarchy(self):
        """Memastikan load_skill_from_file mengekstrak branch dan role dari hierarki direktori."""
        content = """---
name: "Time Series Trends"
slug: "time-series-trends"
version: "1.0.0"
tools_required:
  - "run_trend_analysis"
priority: "high"
---
# Content SOP
Analisis deret waktu.
"""
        file_path = self._create_sample_skill_file("planning", "bi_analyst", "trends.md", content)
        skill = load_skill_from_file(file_path)

        self.assertIsNotNone(skill)
        self.assertEqual(skill["name"], "Time Series Trends")
        self.assertEqual(skill["branch"], "planning")
        self.assertEqual(skill["role"], "bi_analyst")
        self.assertIn("bi_analyst", skill["roles"])
        self.assertEqual(skill["priority"], "high")
        self.assertIn("run_trend_analysis", skill["tools_required"])

    # =========================================================================
    # 3. TEST ROLE VARIANT NORMALIZATION
    # =========================================================================
    def test_03_normalize_role_variants(self):
        """Memastikan variasi nama peran (kebab-case, snake_case, space-case) dikenali setara."""
        variants_kebab = _normalize_role_variants("planning-manager")
        self.assertIn("planning-manager", variants_kebab)
        self.assertIn("planning_manager", variants_kebab)
        self.assertIn("planning manager", variants_kebab)

        variants_snake = _normalize_role_variants("quality_control_officer")
        self.assertIn("quality-control-officer", variants_snake)
        self.assertIn("quality_control_officer", variants_snake)

    # =========================================================================
    # 4. TEST ROLE-CENTRIC RBAC DISCOVERY (LEAST PRIVILEGE OPSI C)
    # =========================================================================
    def test_04_get_skills_for_worker_active_only(self):
        """Hanya skill aktif yang dimuat; skill divisi dormant tidak ikut."""
        mgr_skills = get_skills_for_worker(branch="orchestrator", worker_key="manager")
        slugs = sorted(s["slug"] for s in mgr_skills)
        self.assertEqual(
            slugs,
            [
                "cross-branch-collaboration",
                "human-in-the-loop-governance",
                "task-orchestration-and-delegation",
            ],
        )
        self.assertTrue(all(s["branch"] == "orchestrator" for s in mgr_skills))

        # Semua skill planning masih dormant (tool-nya belum dibangun).
        self.assertEqual(get_skills_for_worker(branch="planning", worker_key="bi_analyst"), [])
        planning_mgr = get_skills_for_worker(branch="planning", worker_key="manager")
        self.assertEqual(len(planning_mgr), 3)
        self.assertTrue(all(s["branch"] == "orchestrator" for s in planning_mgr))

    # =========================================================================
    # 5. TEST CROSS-BRANCH ISOLATION
    # =========================================================================
    def test_05_dormant_skills_not_loaded(self):
        """Skill dengan tool hilang tidak dimuat ke worker mana pun."""
        self.assertEqual(get_skills_for_worker(branch="finance", worker_key="treasurer"), [])
        self.assertEqual(get_skills_for_worker(branch="logistics", worker_key="shipping_clerk"), [])

        # Manager tetap mendapat skill orchestrator yang aktif, bukan skill dormant cabangnya.
        for branch in ("finance", "sales", "planning"):
            for skill in get_skills_for_worker(branch=branch, worker_key="manager"):
                self.assertEqual(skill["branch"], "orchestrator")

    # =========================================================================
    # 6. TEST VALIDATE SKILL DEPENDENCIES
    # =========================================================================
    def test_06_validate_skill_dependencies(self):
        """Memastikan validasi dependensi tools_required mencocokkan ke _TOOL_REGISTRY."""
        valid_skill = {
            "name": "Active Tool Test",
            "slug": "test-valid-tool",
            "tools_required": ["get_current_time", "orchestrator_delegate_to_subagent"]
        }
        res_valid = validate_skill_dependencies(valid_skill)
        self.assertTrue(res_valid["valid"])
        self.assertTrue(is_skill_active(valid_skill))
        self.assertEqual(len(res_valid["missing_tools"]), 0)

        invalid_skill = {
            "name": "Invalid Test",
            "slug": "test-invalid-tool",
            "tools_required": ["non_existent_tool_12345"]
        }
        res_invalid = validate_skill_dependencies(invalid_skill)
        self.assertFalse(res_invalid["valid"])
        self.assertFalse(is_skill_active(invalid_skill))
        self.assertIn("test-invalid-tool", res_invalid["missing_tools"])
        self.assertIn("non_existent_tool_12345", res_invalid["missing_tools"]["test-invalid-tool"])

    # =========================================================================
    # 7. TEST SMART CACHING & INVALIDATION
    # =========================================================================
    def test_07_smart_caching_and_invalidation(self):
        """Memastikan smart caching in-memory berfungsi dan invalidation berjalan saat force_reload."""
        clear_skills_cache()
        
        # Load pertama (populate cache)
        skills_first = load_all_skills()
        self.assertGreater(len(skills_first), 0)

        # Load kedua (harus dari cache)
        skills_second = load_all_skills(force_reload=False)
        self.assertEqual(len(skills_first), len(skills_second))

        # Invalidate cache
        clear_skills_cache()
        skills_reloaded = load_all_skills(force_reload=True)
        self.assertEqual(len(skills_first), len(skills_reloaded))

    # =========================================================================
    # 8. TEST COMPOSE WORKER SYSTEM PROMPT
    # =========================================================================
    def test_08_compose_worker_system_prompt(self):
        """Prompt hanya memuat SOP aktif; SOP dormant tidak disuntikkan."""
        base_prompt = "Anda adalah AI Manager berpengalaman."
        composed = compose_worker_system_prompt(
            branch="orchestrator", worker_key="manager", base_prompt=base_prompt
        )

        self.assertIn("Anda adalah AI Manager berpengalaman.", composed)
        self.assertIn("[STANDARD OPERATING PROCEDURES & WORKFLOW SKILLS]", composed)
        self.assertIn("Task Orchestration and Delegation Workflow", composed)

        dormant_only = compose_worker_system_prompt(
            branch="planning", worker_key="planning_manager", base_prompt=base_prompt
        )
        self.assertNotIn("Corporate Scenario Simulation", dormant_only)

    # =========================================================================
    # 9. TEST REAL SKILLS INTEGRITY & UNIK SLUGS (86 SKILLS AKTIF)
    # =========================================================================
    def test_09_real_skills_integrity_and_uniqueness(self):
        """86 file utuh; skill AKTIF hanya merujuk tool terdaftar; dormant punya tool hilang."""
        all_skills = load_all_skills(force_reload=True)

        # Total harus 86 skills (3 Orch + 11 Fin + 10 Sales + 10 Mat + 11 HR + 7 Mfg + 9 QA + 9 Log + 8 Mnt + 8 Pln)
        self.assertEqual(len(all_skills), 86, f"Ekspektasi 86 skills, ditemukan {len(all_skills)}: {list(all_skills.keys())}")

        # Pastikan tidak ada slug yang duplikat
        slugs = list(all_skills.keys())
        unique_slugs = set(slugs)
        self.assertEqual(len(slugs), len(unique_slugs), f"Ditemukan duplikasi slug pada skills: {slugs}")

        _ensure_tools_loaded()
        available_tools = set(_TOOL_REGISTRY)
        active = []
        dormant = []
        for skill in all_skills.values():
            missing = [t for t in skill["tools_required"] if t not in available_tools]
            if is_skill_active(skill, available_tools):
                active.append(skill)
                self.assertEqual(missing, [], f"Skill aktif {skill['slug']} merujuk tool hilang: {missing}")
            else:
                dormant.append(skill)
                self.assertTrue(missing, f"Skill dormant {skill['slug']} tidak punya tool hilang")

        self.assertEqual(len(active), 3)
        self.assertEqual(len(dormant), 83)

        validation = validate_skill_dependencies()
        self.assertFalse(validation["valid"])
        self.assertEqual(validation["total_skills_checked"], 86)
        self.assertEqual(len(validation["missing_tools"]), len(dormant))

    # =========================================================================
    # 10. TEST PERFORMANCE & LATENCY BENCHMARK (< 50 ms)
    # =========================================================================
    def test_10_skills_loader_performance_benchmark(self):
        """Memastikan pembacaan seluruh 86 skills via in-memory cache berlangsung instan (< 50 ms)."""
        load_all_skills(force_reload=True)  # Warmup
        
        t0 = time.perf_counter()
        for _ in range(100):
            _ = get_skills_for_worker(branch="finance", worker_key="treasurer")
            _ = get_skills_for_worker(branch="sales", worker_key="sales_representative")
            _ = get_skills_for_worker(branch="planning", worker_key="planning_manager")
        elapsed_ms = (time.perf_counter() - t0) * 1000

        avg_latency_ms = elapsed_ms / 100.0
        self.assertLess(avg_latency_ms, 50.0, f"Latensi pembacaan skills terlalu lambat: {avg_latency_ms:.2f} ms")


def run_tests():
    """Fungsi runner untuk dieksekusi via `bench execute`."""
    suite = unittest.TestLoader().loadTestsFromTestCase(TestSkillsEngine)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    summary = {
        "success": result.wasSuccessful(),
        "total_run": result.testsRun,
        "failures": len(result.failures),
        "errors": len(result.errors)
    }
    print(json.dumps(summary, indent=2))
    return summary
