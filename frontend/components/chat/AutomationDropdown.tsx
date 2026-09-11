"use client";

import React, { useEffect, useRef, useState, useMemo } from "react";
import {
  Zap,
  ChevronDown,
  Sparkles,
  BarChart3,
  Clock,
  TrendingUp,
  Calculator,
  Award,
  LineChart,
  AlertTriangle,
  Kanban,
  Package,
  Layers,
  Hourglass,
  DollarSign,
  UserCheck,
  Users,
  Gauge,
  ClipboardList,
  Coins,
  Timer,
  Microscope,
  Activity,
  CheckCircle2,
  PieChart,
  Truck,
  Boxes,
  Fuel,
  Tags,
  Wrench,
  Cpu,
  ListTodo,
  Sliders,
  Target,
  Scale,
  Search,
  ArrowUpRight
} from "lucide-react";
import { getAutomationsForBranch, AutomationPreset } from "@/lib/automations";
import styles from "./AutomationDropdown.module.css";

const ICON_MAP: Record<string, React.ElementType> = {
  BarChart3,
  Clock,
  TrendingUp,
  Calculator,
  Award,
  LineChart,
  AlertTriangle,
  Kanban,
  Package,
  Layers,
  Hourglass,
  DollarSign,
  UserCheck,
  Users,
  Gauge,
  ClipboardList,
  Coins,
  Timer,
  Microscope,
  Activity,
  CheckCircle2,
  PieChart,
  Truck,
  Boxes,
  Fuel,
  Tags,
  Wrench,
  Cpu,
  ListTodo,
  Sliders,
  Target,
  Scale
};

interface AutomationDropdownProps {
  branchKey: string;
  branchName: string;
  onSelect: (preset: AutomationPreset) => void;
  disabled?: boolean;
}

export function AutomationDropdown({
  branchKey,
  branchName,
  onSelect,
  disabled
}: AutomationDropdownProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedCategory, setSelectedCategory] = useState<string>("all");
  const dropdownRef = useRef<HTMLDivElement>(null);
  const searchInputRef = useRef<HTMLInputElement>(null);

  const automations = useMemo(() => getAutomationsForBranch(branchKey), [branchKey]);

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    }
    if (isOpen) {
      document.addEventListener("mousedown", handleClickOutside);
      setTimeout(() => searchInputRef.current?.focus(), 100);
    }
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
    };
  }, [isOpen]);

  const filteredAutomations = useMemo(() => {
    return automations.filter((item) => {
      const matchCat = selectedCategory === "all" || item.category === selectedCategory;
      const matchQuery =
        item.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
        item.description.toLowerCase().includes(searchQuery.toLowerCase());
      return matchCat && matchQuery;
    });
  }, [automations, selectedCategory, searchQuery]);

  if (!automations || automations.length === 0) return null;

  return (
    <div className={styles.wrapper} ref={dropdownRef}>
      <button
        type="button"
        className={`${styles.trigger} ${isOpen ? styles.triggerActive : ""}`}
        onClick={() => setIsOpen((prev) => !prev)}
        disabled={disabled}
        title="Buka Menu Alur Otomasi Cerdas"
        aria-expanded={isOpen}
      >
        <Zap className={styles.triggerIcon} size={14} />
        <span className={styles.triggerLabel}>Otomasi</span>
        <ChevronDown className={`${styles.chevron} ${isOpen ? styles.chevronRotated : ""}`} size={12} />
      </button>

      {isOpen && (
        <div className={styles.popover}>
          {/* Header Panel */}
          <div className={styles.header}>
            <div className={styles.headerTop}>
              <div className={styles.titleWrap}>
                <Sparkles className={styles.sparkleIcon} size={15} />
                <span className={styles.title}>Katalog Otomasi {branchName}</span>
              </div>
              <span className={styles.badge}>{automations.length} Alur</span>
            </div>

            {/* Search Input */}
            <div className={styles.searchWrap}>
              <Search size={13} className={styles.searchIcon} />
              <input
                ref={searchInputRef}
                type="text"
                className={styles.searchInput}
                placeholder="Cari alur analitik atau tugas..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
              />
              {searchQuery && (
                <button
                  type="button"
                  className={styles.clearSearch}
                  onClick={() => setSearchQuery("")}
                >
                  ×
                </button>
              )}
            </div>

            {/* Category Filter Pills */}
            <div className={styles.categoryFilters}>
              <button
                type="button"
                className={`${styles.catPill} ${selectedCategory === "all" ? styles.catPillActive : ""}`}
                onClick={() => setSelectedCategory("all")}
              >
                Semua
              </button>
              <button
                type="button"
                className={`${styles.catPill} ${selectedCategory === "analytics" ? styles.catPillActive : ""}`}
                onClick={() => setSelectedCategory("analytics")}
              >
                Analitik
              </button>
              <button
                type="button"
                className={`${styles.catPill} ${selectedCategory === "operational" ? styles.catPillActive : ""}`}
                onClick={() => setSelectedCategory("operational")}
              >
                Operasional
              </button>
              <button
                type="button"
                className={`${styles.catPill} ${selectedCategory === "forecast" ? styles.catPillActive : ""}`}
                onClick={() => setSelectedCategory("forecast")}
              >
                Proyeksi
              </button>
              <button
                type="button"
                className={`${styles.catPill} ${selectedCategory === "audit" ? styles.catPillActive : ""}`}
                onClick={() => setSelectedCategory("audit")}
              >
                Audit
              </button>
            </div>
          </div>

          {/* Items List */}
          <div className={styles.list}>
            {filteredAutomations.length === 0 ? (
              <div className={styles.empty}>
                Tidak ditemukan alur otomasi yang sesuai kriteria pencarian.
              </div>
            ) : (
              filteredAutomations.map((item) => {
                const IconComponent = ICON_MAP[item.iconName] || BarChart3;
                return (
                  <button
                    key={item.id}
                    type="button"
                    className={styles.item}
                    onClick={() => {
                      setIsOpen(false);
                      onSelect(item);
                    }}
                  >
                    <div className={styles.iconContainer}>
                      <IconComponent size={16} className={styles.itemIcon} />
                    </div>
                    <div className={styles.itemContent}>
                      <div className={styles.itemTitleRow}>
                        <span className={styles.itemTitle}>{item.title}</span>
                        <ArrowUpRight size={12} className={styles.arrowIcon} />
                      </div>
                      <p className={styles.itemDesc}>{item.description}</p>
                    </div>
                  </button>
                );
              })
            )}
          </div>
        </div>
      )}
    </div>
  );
}
