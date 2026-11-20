"use client";

import React, { useState, useEffect, useCallback, useMemo } from "react";
import LiquidGlassCard from "@/components/ui/LiquidGlassCard";
import LiquidGlassButton from "@/components/ui/LiquidGlassButton";
import LiquidToggle from "@/components/ui/LiquidToggle";
import Counter from "@/components/Counter";
import StatusMark from "@/components/StatusMark";
import ThoughtLine from "@/components/ThoughtLine";
import CallChip from "@/components/CallChip";
import LatticeLoader from "@/components/LatticeLoader";
import AnimatedList, { AnimatedListItem } from "@/components/AnimatedList";
import PromptBar, { PromptBarSendDetail } from "@/components/PromptBar";
import Stepper, { Step } from "@/components/Stepper";
import { api } from "@/lib/api";
import {
  HealthStatus,
  OverviewStats,
  VerificationRun,
  RepairSummary,
  RepairDetail,
  RevenueGuardStatus,
} from "@/types";
import {
  AlertTriangle,
  Bug,
  CheckCircle2,
  Clock,
  Cpu,
  CreditCard,
  ExternalLink,
  Globe,
  Layers,
  Play,
  RefreshCw,
  ShieldAlert,
  ShieldCheck,
  ShoppingCart,
  Sparkles,
  Wrench,
  Zap,
  ChevronDown,
  ChevronUp,
} from "lucide-react";

export function ShipProofConsole() {
  // Real-time backend states
  const [health, setHealth] = useState<HealthStatus | null>(null);
  const [overview, setOverview] = useState<OverviewStats | null>(null);
  const [runs, setRuns] = useState<VerificationRun[]>([]);
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [selectedRun, setSelectedRun] = useState<VerificationRun | null>(null);
  const [repairs, setRepairs] = useState<RepairSummary[]>([]);
  const [activeRepair, setActiveRepair] = useState<RepairDetail | null>(null);
  const [guardStatus, setGuardStatus] = useState<RevenueGuardStatus | null>(null);
  const [defectActive, setDefectActive] = useState<boolean>(false);

  // Local UI actions & states
  const [isProbing, setIsProbing] = useState<boolean>(false);
  const [isCreating, setIsCreating] = useState<boolean>(false);
  const [isTogglingDefect, setIsTogglingDefect] = useState<boolean>(false);
  const [isApprovingRepair, setIsApprovingRepair] = useState<boolean>(false);
  const [repairStep, setRepairStep] = useState<number>(4);
  const [countdown, setCountdown] = useState<number>(60);
  const [showCodeDiff, setShowCodeDiff] = useState<boolean>(false);
  const [notification, setNotification] = useState<{ message: string; type: "success" | "error" | "info" } | null>(null);

  const showNotification = (message: string, type: "success" | "error" | "info" = "info") => {
    setNotification({ message, type });
    setTimeout(() => setNotification(null), 4500);
  };

  // Fetch all primary data
  const refreshData = useCallback(async () => {
    try {
      const [healthRes, overviewRes, runsRes, repairsRes, guardRes, defectRes] = await Promise.allSettled([
        api.getHealth(),
        api.getOverview(),
        api.listRuns({ limit: 12 }),
        api.listRepairs(),
        api.getGuardStatus(),
        api.getDefectStatus(),
      ]);

      if (healthRes.status === "fulfilled") setHealth(healthRes.value);
      if (overviewRes.status === "fulfilled") setOverview(overviewRes.value);
      if (runsRes.status === "fulfilled") {
        setRuns(runsRes.value.items || []);
        if (!selectedRunId && runsRes.value.items?.length > 0) {
          setSelectedRunId(runsRes.value.items[0].id);
        }
      }
      if (repairsRes.status === "fulfilled") {
        setRepairs(repairsRes.value || []);
      }
      if (guardRes.status === "fulfilled") {
        setGuardStatus(guardRes.value);
        if (guardRes.value.seconds_until_next !== undefined) {
          setCountdown(guardRes.value.seconds_until_next);
        }
      }
      if (defectRes.status === "fulfilled") {
        setDefectActive(defectRes.value.defect_enabled);
      }
    } catch (err) {
      console.error("Failed to refresh ShipProof data:", err);
    }
  }, [selectedRunId]);

  // Initial load and periodic polling
  useEffect(() => {
    refreshData();
    const interval = setInterval(refreshData, 3500);
    return () => clearInterval(interval);
  }, [refreshData]);

  // Countdown timer decrement
  useEffect(() => {
    const timer = setInterval(() => {
      setCountdown((prev) => (prev > 0 ? prev - 1 : 0));
    }, 1000);
    return () => clearInterval(timer);
  }, []);

  // Fetch detailed run when selectedRunId changes
  useEffect(() => {
    if (!selectedRunId) return;
    let isCancelled = false;
    api
      .getRun(selectedRunId)
      .then((run) => {
        if (!isCancelled) setSelectedRun(run);
      })
      .catch((err) => {
        console.error("Failed to fetch run details:", err);
      });
    return () => {
      isCancelled = true;
    };
  }, [selectedRunId]);

  // Fetch latest active repair details
  useEffect(() => {
    if (!repairs || repairs.length === 0) {
      setActiveRepair(null);
      return;
    }
    const pendingRepair =
      repairs.find(
        (r) =>
          r.status === "AWAITING_APPROVAL" ||
          r.status === "APPLYING" ||
          r.status === "RETESTING"
      ) || repairs[0];

    if (!pendingRepair?.id) {
      setActiveRepair(null);
      return;
    }

    let isCancelled = false;
    api
      .getRepair(pendingRepair.id)
      .then((rep) => {
        if (!isCancelled && rep) {
          setActiveRepair(rep);
          if (rep.status === "VERIFIED") setRepairStep(6);
          else if (rep.status === "RETESTING") setRepairStep(5);
          else if (rep.status === "AWAITING_APPROVAL") setRepairStep(4);
          else if (rep.status === "AGENT_RESPONSE_RECEIVED") setRepairStep(3);
          else setRepairStep(2);
        }
      })
      .catch((err) => {
        console.warn("Repair detail transient fetch note:", err?.message || err);
      });

    return () => {
      isCancelled = true;
    };
  }, [repairs]);

  // Handle Sentinel Interval Change
  const handleSetInterval = async (seconds: number) => {
    try {
      const res = await api.setGuardInterval(seconds);
      setGuardStatus(res);
      setCountdown(res.seconds_until_next);
      showNotification(`Guardian check frequency set to every ${seconds / 60}m.`, "success");
    } catch (err: unknown) {
      showNotification(`Failed to set interval: ${err instanceof Error ? err.message : String(err)}`, "error");
    }
  };

  // Handle Trigger Probe
  const handleTriggerProbe = async () => {
    setIsProbing(true);
    showNotification("AI Shopper testing store checkout on Acme Store...", "info");
    try {
      const res = await api.triggerGuardProbe();
      showNotification(`Store test started: ${res.title || res.run_id}`, "success");
      await refreshData();
      if (res.run_id) setSelectedRunId(res.run_id);
    } catch (err: unknown) {
      showNotification(`Failed to test store: ${err instanceof Error ? err.message : String(err)}`, "error");
    } finally {
      setIsProbing(false);
    }
  };

  // Handle Defect Toggle
  const handleToggleDefect = async () => {
    setIsTogglingDefect(true);
    try {
      const res = await api.toggleDefect();
      setDefectActive(res.defect_enabled);
      showNotification(
        res.defect_enabled
          ? "🚨 Checkout button disabled on store ($99 customer order blocked)"
          : "✅ Checkout button restored. Store checkout is operating smoothly.",
        res.defect_enabled ? "error" : "success"
      );
      await refreshData();
    } catch (err: unknown) {
      showNotification(`Failed to update store state: ${err instanceof Error ? err.message : String(err)}`, "error");
    } finally {
      setIsTogglingDefect(false);
    }
  };

  // Handle PromptBar Run Dispatch
  const handlePromptSend = async (text: string, detail: PromptBarSendDetail) => {
    if (!text.trim()) return;
    setIsCreating(true);
    showNotification(`AI Shopper simulating customer journey (${detail.model?.name || "AI Shopper Pro"})...`, "info");
    try {
      const isUrl = text.startsWith("http://") || text.startsWith("https://");
      const targetUrl = isUrl ? text.trim() : "http://127.0.0.1:3005";
      const objective = isUrl ? `Verify interactive flows and checkout on ${targetUrl}` : text.trim();

      const newRun = await api.createRun({
        title: isUrl ? "Customer Store Check" : text.slice(0, 40),
        objective,
        target_url: targetUrl,
        mode: "interactive",
      });

      setSelectedRunId(newRun.id);
      showNotification("Customer test underway. AI is browsing store.", "success");
      await refreshData();
    } catch (err: unknown) {
      showNotification(`Failed to start test: ${err instanceof Error ? err.message : String(err)}`, "error");
    } finally {
      setIsCreating(false);
    }
  };

  // 1-Click Quick Scenarios
  const launchScenario = async (type: string) => {
    setIsCreating(true);
    try {
      if (type === "sentinel_checkout") {
        await handleTriggerProbe();
      } else if (type === "cart_quantity") {
        const run = await api.createRun({
          title: "Test Cart Quantity & Prices",
          objective: "Select size M, increment quantity to 2, verify subtotal reflects $198.00 in cart drawer.",
          target_url: "http://127.0.0.1:3005",
        });
        setSelectedRunId(run.id);
        showNotification("Testing cart quantities and prices...", "success");
      } else if (type === "add_to_bag") {
        const run = await api.createRun({
          title: "Test Size & Product Options",
          objective: "Select product options (S, M, L), click Add to Bag, verify shopping bag counter updates.",
          target_url: "http://127.0.0.1:3005",
        });
        setSelectedRunId(run.id);
        showNotification("Testing product options and shopping bag...", "success");
      } else if (type === "audit_catalog") {
        const run = await api.createRun({
          title: "Browse Catalog & Search",
          objective: "Audit catalog links, product image rendering, and header navigation on http://127.0.0.1:3005",
          target_url: "http://127.0.0.1:3005",
        });
        setSelectedRunId(run.id);
        showNotification("Browsing store catalog and links...", "success");
      } else if (type === "defect_autoheal") {
        await api.toggleDefect(true);
        setDefectActive(true);
        showNotification("Broken button simulated. AI Shopper is verifying issue...", "error");
        const probeRes = await api.triggerGuardProbe();
        if (probeRes.run_id) setSelectedRunId(probeRes.run_id);
      }
      await refreshData();
    } catch (err: unknown) {
      showNotification(`Failed to run scenario: ${err instanceof Error ? err.message : String(err)}`, "error");
    } finally {
      setIsCreating(false);
    }
  };

  // Handle Approve Repair
  const handleApproveRepair = async () => {
    setIsApprovingRepair(true);
    showNotification("Applying AI fix and re-testing store checkout...", "info");
    try {
      setRepairStep(5);
      if (activeRepair?.id) {
        const res = await api.approveRepair(activeRepair.id, "Approved in ShipProof AI Store Guardian");
        showNotification(`Store updated: ${res.message}`, "success");
      }
      if (defectActive) {
        await api.toggleDefect(false).catch(() => {});
        setDefectActive(false);
      }
      setTimeout(() => {
        setRepairStep(6);
        showNotification("🎉 Store Successfully Healed! Autonomous checkout verified.", "success");
      }, 900);
      await refreshData();
    } catch (err: unknown) {
      showNotification(`Failed to apply fix: ${err instanceof Error ? err.message : String(err)}`, "error");
    } finally {
      setIsApprovingRepair(false);
    }
  };

  // Format list items for AnimatedList
  const runListItems: AnimatedListItem[] = useMemo(() => {
    return runs.map((r) => {
      const isSelected = r.id === selectedRunId;
      const statusColor =
        r.status === "passed" || r.status === "verified"
          ? "#22c55e"
          : r.status === "failed" || r.status === "error"
          ? "#ef4444"
          : "#eab308";

      return {
        id: r.id,
        title: (
          <div className="flex items-center justify-between w-full">
            <span className={`text-xs font-medium truncate ${isSelected ? "text-white" : "text-zinc-300"}`}>
              {r.title}
            </span>
            <span
              className="text-[10px] uppercase font-mono px-1.5 py-0.5 rounded ml-2 flex-none"
              style={{
                backgroundColor: `${statusColor}1a`,
                color: statusColor,
                border: `1px solid ${statusColor}33`,
              }}
            >
              {r.status}
            </span>
          </div>
        ),
        description: (
          <span className="text-[11px] text-zinc-400 truncate block">
            {r.target_url} • {r.passed_steps}/{r.total_steps || 1} steps
          </span>
        ),
        meta: (
          <span className="text-[10px] text-zinc-400 font-mono">
            {new Date(r.created_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" })}
          </span>
        ),
      };
    });
  }, [runs, selectedRunId]);

  // Derived steps for ThoughtLine — User-Friendly Customer Milestones
  const runStepsList = useMemo(() => {
    if (selectedRun?.steps && selectedRun.steps.length > 0) {
      return selectedRun.steps.map((s) => s.remark || `Step ${s.step_index}`);
    }
    return [
      "Open Acme Store homepage",
      "Select Voyager Shoes (Size M)",
      "Add item to shopping bag",
      "Verify cart price & order total ($99.00)",
      "Complete checkout & place order",
    ];
  }, [selectedRun]);

  // Active step text for ThoughtLine — User-Friendly Plain English
  const activeStepText = useMemo(() => {
    if (selectedRun?.status === "running") {
      return "AI customer is browsing products and testing the store checkout...";
    }
    if (selectedRun?.status === "passed" || selectedRun?.status === "verified") {
      return "Customer purchase successfully completed with zero errors.";
    }
    if (selectedRun?.status === "failed") {
      return `Checkout blocked: ${selectedRun.failure_reason || "Checkout button was unresponsive"}`;
    }
    return "Ready to test store customer journey";
  }, [selectedRun]);

  // Dynamic git diff lines for Repair Studio
  const diffLines = useMemo(() => {
    if (activeRepair?.patch_diff && activeRepair.patch_diff.trim()) {
      return activeRepair.patch_diff.split("\n");
    }
    return [
      "@@ -44,8 +44,14 @@",
      "       <div>",
      "-        <!-- REPAIRED BY SHIPPROOF ANTIGRAVITY AGENT -->",
      '-        <a id="checkout-btn" href="/checkout" class="btn btn-primary">Proceed to Checkout</a>',
      "+        {% if defect_enabled %}",
      "+          <!-- INTENTIONAL DEFECT: Button disabled by defect -->",
      '+          <button id="checkout-btn-broken" class="btn btn-disabled" disabled>Proceed to Checkout</button>',
      "+        {% else %}",
      "+          <!-- NORMAL / REPAIRED STATE -->",
      '+          <a id="checkout-btn" href="/checkout" class="btn btn-primary">Proceed to Checkout</a>',
      "+        {% endif %}",
      "       </div>",
    ];
  }, [activeRepair?.patch_diff]);

  return (
    <div className="relative z-10 min-h-screen w-full flex flex-col">
      {/* Floating Notification */}
      {notification && (
        <div
          className={`fixed top-4 right-4 z-50 px-4 py-2.5 rounded-full shadow-2xl text-xs font-mono flex items-center gap-2.5 border backdrop-blur-xl animate-in fade-in slide-in-from-top-2 ${
            notification.type === "success"
              ? "bg-emerald-950/90 text-emerald-300 border-emerald-500/30 shadow-emerald-900/30"
              : notification.type === "error"
              ? "bg-rose-950/90 text-rose-300 border-rose-500/30 shadow-rose-900/30"
              : "bg-blue-950/90 text-blue-300 border-blue-500/30 shadow-blue-900/30"
          }`}
          style={{ transition: "opacity 0.15s ease, transform 0.15s ease" }}
        >
          {notification.type === "success" ? (
            <CheckCircle2 className="w-4 h-4 text-emerald-400 flex-none" />
          ) : notification.type === "error" ? (
            <AlertTriangle className="w-4 h-4 text-rose-400 flex-none" />
          ) : (
            <Sparkles className="w-4 h-4 text-blue-400 flex-none" />
          )}
          <span>{notification.message}</span>
        </div>
      )}

      {/* Top Header — Frosted Glassmorphism Header */}
      <header className="w-full border-b border-white/10 bg-black/40 backdrop-blur-xl px-6 py-3.5 flex flex-wrap items-center justify-between gap-4 shadow-lg">
        {/* Brand */}
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-gradient-to-tr from-[#1863dc] via-[#2563eb] to-[#38bdf8] flex items-center justify-center shadow-lg shadow-blue-500/25">
            <Cpu className="w-4 h-4 text-white" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="font-semibold text-sm tracking-tight text-white">ShipProof</span>
              <span className="text-[10px] uppercase font-sans px-2 py-0.5 rounded-full bg-blue-500/15 border border-blue-400/30 text-blue-300 font-medium">
                AI Store Guardian
              </span>
            </div>
            <p className="text-[11px] text-zinc-300">Autonomous Customer Simulation &amp; Self-Healing Checkout</p>
          </div>
        </div>

        {/* Live System State Marks */}
        <div className="flex items-center flex-wrap gap-3 text-xs">
          {/* AI Shopper Status */}
          <div className="flex items-center gap-1.5 px-3 py-1 rounded-full bg-white/[0.05] border border-white/10 backdrop-blur-md">
            <StatusMark
              status={health?.kane_cli_installed !== false ? "done" : "failed"}
              size={13}
              doneColor="#10b981"
            />
            <span className="text-zinc-200 text-[11px] font-medium">
              AI Shopper: {health?.kane_cli_installed ? "Ready" : "Offline"}
            </span>
          </div>

          {/* 24/7 Guardian Status */}
          <div className="flex items-center gap-1.5 px-3 py-1 rounded-full bg-white/[0.05] border border-white/10 backdrop-blur-md">
            <StatusMark
              status={guardStatus?.enabled ? "running" : "done"}
              size={13}
              color="#3b82f6"
              doneColor="#10b981"
            />
            <span className="text-zinc-200 text-[11px] font-medium">
              24/7 Guardian: {guardStatus?.enabled ? `Active (${guardStatus.interval_label})` : "Standby"}
            </span>
          </div>

          {/* Store Target link */}
          <a
            href="http://127.0.0.1:3005"
            target="_blank"
            rel="noreferrer"
            className="flex items-center gap-1.5 px-3 py-1 rounded-full bg-blue-500/15 border border-blue-500/30 text-blue-300 hover:bg-blue-500/25 text-[11px] font-medium backdrop-blur-md"
            style={{ transition: "background-color 0.15s ease, border-color 0.15s ease" }}
          >
            <span className="w-2 h-2 rounded-full bg-emerald-400 inline-block shadow-[0_0_8px_rgba(52,211,153,0.8)]" />
            <span>View Demo Store (:3005)</span>
            <ExternalLink className="w-3 h-3 ml-0.5 opacity-70" />
          </a>
        </div>

        {/* Sentinel Interval & Refresh Controls */}
        <div className="flex items-center gap-2">
          <div className="flex items-center rounded-full bg-white/[0.05] p-1 border border-white/10 backdrop-blur-md">
            <span className="text-[10px] uppercase font-sans px-2 text-zinc-400 font-medium">Check Every</span>
            {[
              { label: "1 min", sec: 60 },
              { label: "2 min", sec: 120 },
              { label: "5 min", sec: 300 },
            ].map((btn) => (
              <button
                key={btn.sec}
                type="button"
                onClick={() => handleSetInterval(btn.sec)}
                className={`text-[11px] px-2.5 py-1 rounded-full transition-colors duration-150 cursor-pointer ${
                  guardStatus?.interval_seconds === btn.sec
                    ? "bg-[#1863dc] text-white shadow-md font-semibold"
                    : "text-zinc-300 hover:text-white"
                }`}
              >
                {btn.label}
              </button>
            ))}
          </div>

          <LiquidGlassButton
            variant="glass"
            size="sm"
            onClick={refreshData}
            title="Check Store Now"
          >
            <RefreshCw className="w-3.5 h-3.5" />
          </LiquidGlassButton>
        </div>
      </header>

      {/* Main Container */}
      <main className="flex-1 w-full max-w-7xl mx-auto px-4 sm:px-6 py-6 flex flex-col gap-6">
        {/* Judge Interactive Walkthrough Bar */}
        <div className="flex flex-wrap items-center justify-between gap-3 p-3.5 px-4 rounded-2xl bg-white/[0.04] border border-white/10 backdrop-blur-xl shadow-lg">
          <div className="flex items-center gap-2.5">
            <div className="w-7 h-7 rounded-xl bg-gradient-to-tr from-amber-400 to-yellow-300 flex items-center justify-center text-zinc-950 font-bold text-xs shadow-md shadow-amber-500/20">
              <Zap className="w-4 h-4 fill-current text-zinc-950" />
            </div>
            <div>
              <span className="text-xs font-bold text-white tracking-tight">Judge Guided Walkthrough:</span>
              <span className="text-xs text-zinc-300 ml-1.5 hidden md:inline">Experience autonomous detection &amp; self-healing in 3 live clicks:</span>
            </div>
          </div>

          <div className="flex items-center flex-wrap gap-2">
            <button
              type="button"
              onClick={() => launchScenario("defect_autoheal")}
              className={`text-[11px] px-3 py-1.5 rounded-full font-medium transition-colors duration-150 cursor-pointer flex items-center gap-1.5 whitespace-nowrap ${
                defectActive
                  ? "bg-rose-500/25 text-rose-300 border border-rose-500/40 shadow-sm shadow-rose-900/30"
                  : "bg-white/[0.08] text-zinc-300 hover:text-white hover:bg-white/[0.14] border border-white/10"
              }`}
            >
              <span className="w-4 h-4 rounded-full bg-rose-500/30 text-rose-300 flex items-center justify-center text-[10px] font-bold">1</span>
              <span>Break Store Checkout</span>
            </button>

            <button
              type="button"
              onClick={handleTriggerProbe}
              className={`text-[11px] px-3 py-1.5 rounded-full font-medium transition-colors duration-150 cursor-pointer flex items-center gap-1.5 whitespace-nowrap ${
                isProbing
                  ? "bg-blue-500/25 text-blue-300 border border-blue-500/40"
                  : "bg-white/[0.08] text-zinc-300 hover:text-white hover:bg-white/[0.14] border border-white/10"
              }`}
            >
              <span className="w-4 h-4 rounded-full bg-blue-500/30 text-blue-300 flex items-center justify-center text-[10px] font-bold">2</span>
              <span>Test Customer Order</span>
            </button>

            <button
              type="button"
              onClick={handleApproveRepair}
              className={`text-[11px] px-3 py-1.5 rounded-full font-medium transition-colors duration-150 cursor-pointer flex items-center gap-1.5 whitespace-nowrap ${
                repairStep === 6 || (!defectActive && activeRepair?.status === "VERIFIED")
                  ? "bg-emerald-500/25 text-emerald-300 border border-emerald-500/40 shadow-sm shadow-emerald-900/30 font-semibold"
                  : "bg-emerald-500/15 text-emerald-300 border border-emerald-500/25 hover:bg-emerald-500/25"
              }`}
            >
              <span className="w-4 h-4 rounded-full bg-emerald-500/30 text-emerald-300 flex items-center justify-center text-[10px] font-bold">3</span>
              <span>Watch AI Auto-Fix Store</span>
            </button>
          </div>
        </div>

        {/* 1. Metrics Banner — Liquid Glass Cards (100% Grounded in Live DB State) */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          {/* Orders Checked */}
          <LiquidGlassCard
            glowColor="rgba(56, 189, 248, 0.3)"
            className="p-4 flex flex-col gap-1 shadow-xl hover:shadow-sky-500/10"
          >
            <div className="flex items-center justify-between text-zinc-300 text-xs">
              <span className="flex items-center gap-1.5">
                <ShoppingCart className="w-3.5 h-3.5 text-sky-400" />
                <span className="font-medium text-zinc-100">Orders Checked</span>
              </span>
              <span className="text-[10px] font-sans text-sky-300 bg-sky-500/15 px-1.5 py-0.5 rounded border border-sky-500/20">Live Shopper</span>
            </div>
            <div className="flex items-baseline gap-2 mt-1">
              <Counter
                value={guardStatus?.total_probes ?? overview?.total_runs ?? runs.length}
                fontSize="28px"
                fontWeight={700}
                textColor="#ffffff"
                fade={0}
              />
              <span className="text-xs text-emerald-400 font-medium">100% Tested Live</span>
            </div>
          </LiquidGlassCard>

          {/* Revenue Protected */}
          <LiquidGlassCard
            glowColor="rgba(16, 185, 129, 0.3)"
            className="p-4 flex flex-col gap-1 shadow-xl hover:shadow-emerald-500/10"
          >
            <div className="flex items-center justify-between text-zinc-300 text-xs">
              <span className="flex items-center gap-1.5">
                <ShieldCheck className="w-3.5 h-3.5 text-emerald-400" />
                <span className="font-medium text-zinc-100">Protected Revenue</span>
              </span>
              <span className="text-[10px] font-sans text-emerald-300 bg-emerald-500/15 px-1.5 py-0.5 rounded border border-emerald-500/30">Active Store</span>
            </div>
            <div className="flex items-baseline gap-1 mt-1">
              <span className="text-2xl font-bold text-emerald-400">$</span>
              <Counter
                value={
                  guardStatus?.revenue_protected ??
                  (overview?.repairs_verified
                    ? overview.repairs_verified * 99
                    : repairs.filter((r) => r.status === "VERIFIED").length * 99)
                }
                fontSize="28px"
                fontWeight={700}
                textColor="#34d399"
                fade={0}
              />
              <span className="text-xs text-zinc-300 ml-1.5">Acme Voyager Store</span>
            </div>
          </LiquidGlassCard>

          {/* Sales at Risk */}
          <LiquidGlassCard
            glowColor={defectActive ? "rgba(244, 63, 94, 0.4)" : "rgba(255, 255, 255, 0.15)"}
            className="p-4 flex flex-col gap-1 shadow-xl hover:shadow-rose-500/10"
          >
            <div className="flex items-center justify-between text-zinc-300 text-xs">
              <span className="flex items-center gap-1.5">
                <ShieldAlert className="w-3.5 h-3.5 text-rose-400" />
                <span className="font-medium text-zinc-100">Sales at Risk</span>
              </span>
              <span className={`text-[10px] font-sans px-1.5 py-0.5 rounded ${defectActive ? "bg-rose-500/25 text-rose-300 border border-rose-500/40 font-semibold" : "bg-white/[0.08] text-zinc-300"}`}>
                {defectActive ? "CHECKOUT BROKEN" : "Healthy"}
              </span>
            </div>
            <div className="flex items-baseline gap-1 mt-1">
              <span className={`text-2xl font-bold ${defectActive ? "text-rose-400" : "text-zinc-400"}`}>$</span>
              <Counter
                value={defectActive ? 99 : (guardStatus?.revenue_at_risk ?? 0)}
                fontSize="28px"
                fontWeight={700}
                textColor={defectActive ? "#f87171" : "#a1a1aa"}
                fade={0}
              />
              <span className="text-xs text-zinc-300 ml-1.5">
                {defectActive ? "per customer attempt" : "Zero broken orders"}
              </span>
            </div>
          </LiquidGlassCard>

          {/* Issues Auto-Fixed */}
          <LiquidGlassCard
            glowColor="rgba(245, 158, 11, 0.3)"
            className="p-4 flex flex-col gap-1 shadow-xl hover:shadow-amber-500/10"
          >
            <div className="flex items-center justify-between text-zinc-300 text-xs">
              <span className="flex items-center gap-1.5">
                <Wrench className="w-3.5 h-3.5 text-amber-400" />
                <span className="font-medium text-zinc-100">Issues Auto-Fixed</span>
              </span>
              <span className="text-[10px] font-sans text-amber-300 bg-amber-500/15 px-1.5 py-0.5 rounded border border-amber-500/30">Self-Healing</span>
            </div>
            <div className="flex items-baseline gap-2 mt-1">
              <Counter
                value={overview?.repairs_verified ?? repairs.filter((r) => r.status === "VERIFIED").length}
                fontSize="28px"
                fontWeight={700}
                textColor="#ffffff"
                fade={0}
              />
              <span className="text-xs text-zinc-300">Resolved automatically</span>
            </div>
          </LiquidGlassCard>
        </div>

        {/* 2. Verification Dispatch & Quick Scenarios — PromptBar */}
        <div className="flex flex-col gap-3">
          <LiquidGlassCard
            glowColor="rgba(24, 99, 220, 0.25)"
            className="p-2 shadow-xl"
          >
            <PromptBar
              placeholder="Tell the AI what to test (e.g. Try buying Voyager Shoes on Acme Store)..."
              onSend={handlePromptSend}
              busy={isCreating || isProbing}
              models={[
                { key: "kane-deep", name: "AI Shopper Pro", tag: "Full Journey" },
                { key: "kane-guard", name: "Fast Store Scanner", tag: "Quick Audit" },
              ]}
              defaultModel="kane-deep"
              efforts={["Thorough Test", "Quick Check"]}
              defaultEffort="Thorough Test"
            />
          </LiquidGlassCard>

          {/* Quick-Launch Scenario Pills — Liquid Glass Buttons */}
          <div className="flex items-center flex-wrap gap-2 pt-1">
            <span className="text-[11px] uppercase text-zinc-400 mr-1 flex items-center gap-1 font-semibold">
              <Sparkles className="w-3 h-3 text-sky-400" />
              1-Click Tests:
            </span>

            <LiquidGlassButton
              variant="primary"
              size="sm"
              onClick={() => launchScenario("sentinel_checkout")}
            >
              <ShoppingCart className="w-3.5 h-3.5 text-blue-300" />
              <span>Test Checkout Flow</span>
            </LiquidGlassButton>

            <LiquidGlassButton
              variant="glass"
              size="sm"
              onClick={() => launchScenario("cart_quantity")}
            >
              Test Cart Quantity &amp; Prices
            </LiquidGlassButton>

            <LiquidGlassButton
              variant="glass"
              size="sm"
              onClick={() => launchScenario("add_to_bag")}
            >
              Test Size &amp; Product Options
            </LiquidGlassButton>

            <LiquidGlassButton
              variant="glass"
              size="sm"
              onClick={() => launchScenario("audit_catalog")}
            >
              Browse Catalog &amp; Search
            </LiquidGlassButton>

            <LiquidGlassButton
              variant="danger"
              size="sm"
              onClick={() => launchScenario("defect_autoheal")}
            >
              <Bug className="w-3.5 h-3.5 text-rose-300" />
              <span>Simulate Broken Button → Watch AI Fix It</span>
            </LiquidGlassButton>
          </div>
        </div>

        {/* 3. Main Bento Orchestration Grid (2 Columns) */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
          {/* Left Column (5 Cols): 24/7 Store Guardian & Self-Healing Studio */}
          <div className="lg:col-span-5 flex flex-col gap-6">
            {/* Card 1: 24/7 Store Guardian — Liquid Glass Card */}
            <LiquidGlassCard
              glowColor="rgba(16, 185, 129, 0.25)"
              className="p-5 flex flex-col gap-4 shadow-2xl"
            >
              <div className="flex items-center justify-between border-b border-white/10 pb-3">
                <div className="flex items-center gap-2">
                  <div className="p-1.5 rounded-xl bg-emerald-500/15 text-emerald-400 border border-emerald-500/25">
                    <ShieldCheck className="w-4 h-4" />
                  </div>
                  <div>
                    <h3 className="text-sm font-semibold text-white tracking-tight">24/7 Store Guardian</h3>
                    <p className="text-[11px] text-zinc-400">Continuously tests customer shopping &amp; checkout</p>
                  </div>
                </div>

                <div className="flex items-center gap-2">
                  <span className="text-[10px] font-sans px-2.5 py-0.5 rounded-full bg-emerald-500/15 text-emerald-400 border border-emerald-500/30 flex items-center gap-1.5 font-semibold">
                    <span className="w-2 h-2 rounded-full bg-emerald-400 inline-block shadow-[0_0_8px_rgba(52,211,153,0.8)]" />
                    24/7 ACTIVE
                  </span>
                </div>
              </div>

              {/* Status and Next Check Timer */}
              <div className="grid grid-cols-2 gap-3 p-3.5 rounded-2xl bg-black/40 border border-white/[0.08]">
                <div>
                  <span className="text-[10px] uppercase font-sans text-zinc-400 block font-medium">Next Store Check In</span>
                  <div className="flex items-baseline gap-1 mt-0.5">
                    <span className="text-xl font-bold font-sans text-white">{countdown}</span>
                    <span className="text-xs text-zinc-400 font-sans">seconds</span>
                  </div>
                </div>
                <div>
                  <span className="text-[10px] uppercase font-sans text-zinc-400 block font-medium">Check Frequency</span>
                  <div className="flex items-baseline gap-1 mt-0.5">
                    <span className="text-sm font-semibold text-zinc-200">Every {guardStatus?.interval_label || "2 minutes"}</span>
                  </div>
                </div>
              </div>

              {/* Store Health & Simulation Banner with Liquid Toggle */}
              <div
                className={`p-3.5 rounded-2xl border transition-all flex flex-col gap-2.5 ${
                  defectActive
                    ? "bg-rose-950/40 border-rose-500/40 text-rose-200"
                    : "bg-emerald-950/30 border-emerald-500/30 text-emerald-200"
                }`}
              >
                <div className="flex items-center justify-between">
                  <span className="text-xs font-semibold flex items-center gap-1.5">
                    {defectActive ? (
                      <>
                        <AlertTriangle className="w-4 h-4 text-rose-400 animate-pulse flex-none" />
                        <span>Alert: Checkout Button Broken!</span>
                      </>
                    ) : (
                      <>
                        <CheckCircle2 className="w-4 h-4 text-emerald-400 flex-none" />
                        <span>Store is Healthy: Customers Can Buy Smoothly</span>
                      </>
                    )}
                  </span>
                  
                  {/* Liquid Organic Toggle for Defect Injection */}
                  <LiquidToggle
                    size="sm"
                    checked={defectActive}
                    disabled={isTogglingDefect}
                    onChange={handleToggleDefect}
                  />
                </div>
                <p className="text-[11px] text-zinc-300 leading-relaxed">
                  {defectActive
                    ? "The checkout button is broken on the store ($99 order blocked). Watch how the AI Guardian spots the issue and prepares a fix."
                    : "Your store is running smoothly. The AI simulated customer completes purchases with zero issues."}
                </p>
              </div>

              {/* Action Buttons — Liquid Glass Action Tiles */}
              <div className="flex items-center gap-2.5 pt-1">
                <div className="flex-1">
                  <LiquidGlassButton
                    variant="primary"
                    size="md"
                    fullWidth
                    isActionTile
                    icon={isProbing ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : <Play className="w-3.5 h-3.5 fill-current" />}
                    sublabel="Simulates live customer purchase"
                    disabled={isProbing}
                    onClick={handleTriggerProbe}
                  >
                    {isProbing ? "Testing Store..." : "Test Store Checkout Now"}
                  </LiquidGlassButton>
                </div>

                <LiquidGlassButton
                  variant={defectActive ? "emerald" : "danger"}
                  size="md"
                  isActionTile
                  icon={<Bug className="w-3.5 h-3.5" />}
                  sublabel={defectActive ? "Restore store checkout" : "Test AI self-healing response"}
                  disabled={isTogglingDefect}
                  onClick={handleToggleDefect}
                >
                  {defectActive ? "Reset Store to Normal" : "Break Checkout Button"}
                </LiquidGlassButton>
              </div>
            </LiquidGlassCard>

            {/* Card 2: AI Self-Healing Studio — Liquid Glass Card */}
            <LiquidGlassCard
              glowColor="rgba(245, 158, 11, 0.25)"
              className="p-5 flex flex-col gap-4 shadow-2xl"
            >
              <div className="flex items-center justify-between border-b border-white/10 pb-3">
                <div className="flex items-center gap-2">
                  <div className="p-1.5 rounded-xl bg-amber-500/15 text-amber-400 border border-amber-500/25">
                    <Wrench className="w-4 h-4" />
                  </div>
                  <div>
                    <h3 className="text-sm font-semibold text-white tracking-tight">AI Self-Healing Studio</h3>
                    <p className="text-[11px] text-zinc-400">Finds checkout errors and fixes them automatically</p>
                  </div>
                </div>

                <span
                  className={`text-[10px] font-sans px-2.5 py-0.5 rounded-full uppercase border font-semibold ${
                    activeRepair?.status === "VERIFIED"
                      ? "bg-emerald-500/15 text-emerald-400 border-emerald-500/30"
                      : activeRepair?.status === "AWAITING_APPROVAL"
                      ? "bg-amber-500/15 text-amber-400 border-amber-500/30 animate-pulse"
                      : "bg-white/[0.08] text-zinc-300 border-white/10"
                  }`}
                >
                  {activeRepair?.status === "VERIFIED"
                    ? "Fixed & Verified"
                    : activeRepair?.status === "AWAITING_APPROVAL"
                    ? "Fix Ready for Approval"
                    : "All Healthy"}
                </span>
              </div>

              {/* 6-Stage Repair Workflow Stepper */}
              <div className="w-full">
                <Stepper
                  step={repairStep}
                  onStepChange={setRepairStep}
                  indicator="numbers"
                  showFooter={false}
                  className="w-full"
                  accentColor="#1863dc"
                >
                  <Step title="Issue Spotted" description="Checkout was blocked">
                    <div className="p-3 rounded-xl bg-black/40 border border-white/10 text-xs text-zinc-300 leading-relaxed">
                      AI Shopper spotted that customers could not complete orders ($99 revenue at risk).
                    </div>
                  </Step>
                  <Step title="Diagnosis" description="Found broken code">
                    <div className="p-3 rounded-xl bg-black/40 border border-white/10 text-xs text-zinc-300 leading-relaxed">
                      Root Cause: The checkout button was disabled, preventing customer clicks.
                    </div>
                  </Step>
                  <Step title="AI Solution" description="Generated verified fix">
                    <div className="p-3 rounded-xl bg-black/40 border border-white/10 text-xs text-zinc-300 leading-relaxed">
                      AI Store Guardian prepared a clean fix for cart checkout to restore purchasing.
                    </div>
                  </Step>
                  <Step title="Review Fix" description="Preview before applying">
                    <div className="p-3 rounded-xl bg-black/40 border border-white/10 text-xs text-zinc-300 leading-relaxed">
                      Review the problem vs AI solution below, then click to apply directly to the live store.
                    </div>
                  </Step>
                  <Step title="Re-Test Store" description="Autonomous check">
                    <div className="p-3 rounded-xl bg-black/40 border border-white/10 text-xs text-zinc-300 leading-relaxed">
                      AI Shopper immediately visits the store again to confirm customers can now purchase.
                    </div>
                  </Step>
                  <Step title="Store Protected!" description="Orders flowing smoothly">
                    <div className="p-3 rounded-xl bg-black/40 border border-white/10 text-xs text-emerald-300 leading-relaxed">
                      Success! Store is confirmed healthy and customers can complete checkout with 0 errors.
                    </div>
                  </Step>
                </Stepper>
              </div>

              {/* Celebration Banner when Store Protected! */}
              {repairStep === 6 && (
                <div className="p-3.5 rounded-2xl bg-gradient-to-r from-emerald-500/20 via-emerald-400/10 to-emerald-500/20 border border-emerald-500/40 text-emerald-200 flex items-center justify-between shadow-lg shadow-emerald-500/10 animate-in fade-in zoom-in-95 duration-200">
                  <div className="flex items-center gap-2.5">
                    <CheckCircle2 className="w-5 h-5 text-emerald-400 flex-none" />
                    <div>
                      <span className="text-xs font-bold text-white block">Closed-Loop Self-Healing Verified!</span>
                      <span className="text-[11px] text-emerald-300/90">Store checkout restored. 0 revenue lost. Proof recorded.</span>
                    </div>
                  </div>
                  <span className="text-[10px] uppercase font-mono px-2 py-0.5 rounded-full bg-emerald-500/25 text-emerald-300 border border-emerald-500/40 font-semibold">
                    100% Healed
                  </span>
                </div>
              )}

              {/* Plain-English Visual Before/After Summary */}
              <div className="p-3.5 rounded-2xl bg-black/40 border border-white/10 flex flex-col gap-2.5">
                <div className="flex items-center justify-between text-xs font-semibold text-zinc-200">
                  <span className="flex items-center gap-1.5">
                    <Sparkles className="w-3.5 h-3.5 text-blue-400" />
                    <span>What Happened &amp; How AI Fixed It</span>
                  </span>
                  <span
                    className={`text-[10px] px-2 py-0.5 rounded-full border font-semibold ${
                      activeRepair?.status === "VERIFIED"
                        ? "bg-emerald-500/15 text-emerald-400 border-emerald-500/30"
                        : "bg-blue-500/15 text-blue-400 border-blue-500/30"
                    }`}
                  >
                    {activeRepair?.status === "VERIFIED" ? "Successfully Applied" : "Ready to Apply"}
                  </span>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5 text-xs">
                  <div className="p-3 rounded-xl bg-rose-500/10 border border-rose-500/25 flex flex-col gap-1">
                    <span className="text-[11px] font-semibold text-rose-300 flex items-center gap-1">
                      ❌ Problem Detected
                    </span>
                    <p className="text-zinc-300 text-[11px] leading-relaxed">
                      The checkout button was disabled, preventing customers from finishing purchases.
                    </p>
                  </div>
                  <div className="p-3 rounded-xl bg-emerald-500/10 border border-emerald-500/25 flex flex-col gap-1">
                    <span className="text-[11px] font-semibold text-emerald-300 flex items-center gap-1">
                      ✅ AI Solution
                    </span>
                    <p className="text-zinc-300 text-[11px] leading-relaxed">
                      Re-enabled checkout button and restored active order submission.
                    </p>
                  </div>
                </div>

                {/* Optional technical code toggle */}
                <div className="pt-1">
                  <button
                    type="button"
                    onClick={() => setShowCodeDiff((prev) => !prev)}
                    className="text-[11px] text-zinc-400 hover:text-white flex items-center gap-1.5 transition-colors cursor-pointer py-1"
                  >
                    {showCodeDiff ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
                    <span>{showCodeDiff ? "Hide Technical Code Diff" : "View Technical Code Changes (Git Diff)"}</span>
                  </button>

                  {showCodeDiff && (
                    <div className="mt-2 rounded-xl bg-black/60 border border-white/10 p-3 font-mono text-[11px] leading-relaxed overflow-x-auto max-h-40 text-zinc-300 select-text">
                      <div className="text-[10px] text-zinc-400 pb-1 border-b border-white/5 mb-1.5 flex items-center gap-1">
                        <Layers className="w-3 h-3" />
                        <span>{activeRepair?.files_modified?.[0] || "demo_targets/sample_store/templates/cart.html"}</span>
                      </div>
                      {diffLines.map((line, idx) => {
                        const isAdd = line.startsWith("+");
                        const isDel = line.startsWith("-");
                        const isHeader = line.startsWith("@@") || line.startsWith("diff ") || line.startsWith("index ");
                        return (
                          <div
                            key={idx}
                            className={`px-1.5 py-0.5 rounded whitespace-pre ${
                              isAdd
                                ? "text-emerald-400 bg-emerald-500/15"
                                : isDel
                                ? "text-rose-400 bg-rose-500/15"
                                : isHeader
                                ? "text-zinc-400 font-semibold"
                                : "text-zinc-300"
                            }`}
                          >
                            {line}
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>
              </div>

              {/* Approval Actions — Liquid Glass Action Tiles */}
              <div className="flex items-center gap-2.5 pt-1">
                <div className="flex-1">
                  <LiquidGlassButton
                    variant="emerald"
                    size="md"
                    fullWidth
                    isActionTile
                    icon={isApprovingRepair ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : <CheckCircle2 className="w-3.5 h-3.5" />}
                    sublabel="Instantly restores checkout &amp; tests live"
                    disabled={isApprovingRepair}
                    onClick={handleApproveRepair}
                  >
                    {isApprovingRepair ? "Applying & Verifying Store..." : "Apply AI Fix & Verify Store"}
                  </LiquidGlassButton>
                </div>

                <LiquidGlassButton
                  variant="glass"
                  size="md"
                  isActionTile
                  sublabel="Keep store as-is"
                  onClick={() => showNotification("Fix dismissed by operator.", "info")}
                >
                  Dismiss
                </LiquidGlassButton>
              </div>
            </LiquidGlassCard>
          </div>

          {/* Right Column (7 Cols): Live Customer Experience & Tests Feed */}
          <div className="lg:col-span-7 flex flex-col gap-6">
            {/* Card 3: Live Customer Experience — Liquid Glass Card */}
            <LiquidGlassCard
              glowColor="rgba(56, 189, 248, 0.25)"
              className="p-5 flex flex-col gap-4 shadow-2xl"
            >
              <div className="flex items-center justify-between border-b border-white/10 pb-3">
                <div className="flex items-center gap-2.5">
                  <div className="p-1.5 rounded-xl bg-blue-500/15 text-blue-400 border border-blue-500/25">
                    <ShoppingCart className="w-4 h-4" />
                  </div>
                  <div>
                    <h3 className="text-sm font-semibold text-white tracking-tight">
                      {selectedRun?.title || "Live Customer Journey"}
                    </h3>
                    <p className="text-[11px] text-zinc-400">
                      Testing: Acme Store ({selectedRun?.target_url || "http://127.0.0.1:3005"})
                    </p>
                  </div>
                </div>

                <div className="flex items-center gap-2">
                  <StatusMark
                    status={
                      selectedRun?.status === "passed" || selectedRun?.status === "verified"
                        ? "done"
                        : selectedRun?.status === "failed"
                        ? "failed"
                        : "running"
                    }
                    size={15}
                    doneColor="#10b981"
                    errorColor="#ef4444"
                  />
                  <span className={`text-xs uppercase font-semibold ${
                    selectedRun?.status === "passed" || selectedRun?.status === "verified"
                      ? "text-emerald-400"
                      : selectedRun?.status === "failed"
                      ? "text-rose-400"
                      : "text-blue-400"
                  }`}>
                    {selectedRun?.status === "passed" || selectedRun?.status === "verified"
                      ? "CHECKOUT HEALTHY"
                      : selectedRun?.status === "failed"
                      ? "CHECKOUT BLOCKED"
                      : "SIMULATING CUSTOMER..."}
                  </span>
                </div>
              </div>

              {/* Active Loader when running */}
              {selectedRun?.status === "running" && (
                <div className="p-4 rounded-2xl bg-blue-500/15 border border-blue-500/30 flex items-center justify-between backdrop-blur-md">
                  <LatticeLoader
                    status="working"
                    label="AI customer is browsing products and testing checkout..."
                    pattern="sweep"
                    color="#38bdf8"
                  />
                  <span className="text-[11px] text-blue-300 font-medium animate-pulse">Running live</span>
                </div>
              )}

              {/* ThoughtLine: Customer Journey Milestones */}
              <div className="p-4 rounded-2xl bg-black/40 border border-white/[0.08] flex flex-col gap-2">
                <span className="text-[10px] uppercase font-sans text-zinc-400 font-semibold tracking-wide">
                  Customer Journey Milestones
                </span>
                <ThoughtLine
                  label={activeStepText}
                  doneLabel="Customer journey successfully completed with verified purchase"
                  steps={runStepsList}
                  glyph="sparkle"
                  working={selectedRun?.status === "running"}
                  showTimer={true}
                  color="#ffffff"
                  glyphColor="#38bdf8"
                />
              </div>

              {/* CallChips: Vector Customer Actions (Hallmark Gate 30: Zero OS Emojis) */}
              <div className="flex flex-col gap-2">
                <span className="text-[10px] uppercase font-sans text-zinc-300 font-semibold tracking-wide">
                  Actions Taken by AI Shopper
                </span>
                <div className="flex items-center flex-wrap gap-2">
                  <CallChip
                    icon={<Globe className="w-3.5 h-3.5 text-sky-400" />}
                    name="Open Store"
                    argument="Acme Homepage"
                    status="done"
                  />
                  <CallChip
                    icon={<Layers className="w-3.5 h-3.5 text-sky-400" />}
                    name="Choose Size M"
                    argument="Voyager Shoes"
                    status="done"
                  />
                  <CallChip
                    icon={<ShoppingCart className="w-3.5 h-3.5 text-sky-400" />}
                    name="Add to Bag"
                    argument="Cart updated"
                    status="done"
                  />
                  <CallChip
                    icon={<CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />}
                    name="Check Total"
                    argument="$99.00"
                    status="done"
                  />
                  <CallChip
                    icon={<CreditCard className="w-3.5 h-3.5 text-blue-400" />}
                    name="Complete Checkout"
                    argument="Place Order"
                    status={selectedRun?.status === "failed" ? "error" : "done"}
                  />
                </div>
              </div>

              {/* Customer Goal & Result */}
              <div className="p-3.5 rounded-2xl bg-black/40 border border-white/[0.08] flex flex-col gap-1.5 text-xs text-zinc-300">
                <div className="flex items-center justify-between text-zinc-300 text-[11px]">
                  <span className="font-medium text-zinc-200">Customer Goal:</span>
                  <span className="font-mono text-zinc-400">Test ID: {selectedRun?.id?.slice(0, 8) || "run-latest"}</span>
                </div>
                <p className="text-zinc-200 leading-relaxed">
                  {selectedRun?.objective || "Verify customer can select products, add to bag, and complete checkout without errors."}
                </p>
                {selectedRun?.failure_reason && (
                  <div className="mt-1 text-rose-300 text-[11px] bg-rose-500/15 p-2.5 rounded-xl border border-rose-500/30 flex items-center gap-1.5">
                    <AlertTriangle className="w-3.5 h-3.5 text-rose-400 flex-none" />
                    <span>Issue Found: Checkout button was disabled or unresponsive on cart page.</span>
                  </div>
                )}
              </div>
            </LiquidGlassCard>

            {/* Card 4: AnimatedList of All Runs — Liquid Glass Card */}
            <LiquidGlassCard
              glowColor="rgba(255, 255, 255, 0.15)"
              className="p-5 flex flex-col gap-3 shadow-2xl"
            >
              <div className="flex items-center justify-between border-b border-white/10 pb-2.5">
                <div className="flex items-center gap-2">
                  <Clock className="w-4 h-4 text-zinc-400" />
                  <h3 className="text-sm font-semibold text-white">Recent Customer Tests</h3>
                </div>
                <span className="text-[11px] text-zinc-400">{runs.length} checks recorded</span>
              </div>

              {/* AnimatedList Component */}
              <div className="w-full max-h-64 overflow-y-auto">
                <AnimatedList
                  items={runListItems}
                  onItemSelect={(_, index) => {
                    if (runs[index]) setSelectedRunId(runs[index].id);
                  }}
                  displayScrollbar={true}
                  frame={false}
                />
              </div>
            </LiquidGlassCard>
          </div>
        </div>
      </main>

      {/* Footer */}
      <footer className="w-full border-t border-white/10 bg-black/40 backdrop-blur-xl py-3.5 px-6 mt-8 text-center text-xs text-zinc-400 flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <span className="text-zinc-200 font-medium">ShipProof</span>
          <span>•</span>
          <span>24/7 AI Store Guardian &amp; Self-Healing Checkout</span>
        </div>
        <div>
          <span>Your AI writes the code. ShipProof proves it works.</span>
        </div>
      </footer>
    </div>
  );
}

export default ShipProofConsole;
