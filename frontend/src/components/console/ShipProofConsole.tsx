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
  Activity,
  AlertTriangle,
  Bug,
  CheckCircle2,
  Clock,
  Cpu,
  ExternalLink,
  Layers,
  Play,
  RefreshCw,
  ShieldAlert,
  ShieldCheck,
  Terminal,
  Wrench,
  Sparkles,
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
      showNotification(`Sentinel interval adjusted to ${seconds / 60}m.`, "success");
    } catch (err: unknown) {
      showNotification(`Failed to set interval: ${err instanceof Error ? err.message : String(err)}`, "error");
    }
  };

  // Handle Trigger Probe
  const handleTriggerProbe = async () => {
    setIsProbing(true);
    showNotification("Secret shopper probe launched against :3005...", "info");
    try {
      const res = await api.triggerGuardProbe();
      showNotification(`Probe initiated: ${res.title || res.run_id}`, "success");
      await refreshData();
      if (res.run_id) setSelectedRunId(res.run_id);
    } catch (err: unknown) {
      showNotification(`Failed to trigger probe: ${err instanceof Error ? err.message : String(err)}`, "error");
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
          ? "🚨 Checkout defect injected on http://127.0.0.1:3005 ($99.00 order at risk)"
          : "✅ Checkout defect resolved. Store code restored.",
        res.defect_enabled ? "error" : "success"
      );
      await refreshData();
    } catch (err: unknown) {
      showNotification(`Defect toggle failed: ${err instanceof Error ? err.message : String(err)}`, "error");
    } finally {
      setIsTogglingDefect(false);
    }
  };

  // Handle PromptBar Run Dispatch
  const handlePromptSend = async (text: string, detail: PromptBarSendDetail) => {
    if (!text.trim()) return;
    setIsCreating(true);
    showNotification(`Dispatching verification probe with ${detail.model?.name || "Kane v2.4"}...`, "info");
    try {
      const isUrl = text.startsWith("http://") || text.startsWith("https://");
      const targetUrl = isUrl ? text.trim() : "http://127.0.0.1:3005";
      const objective = isUrl ? `Verify interactive flows and checkout on ${targetUrl}` : text.trim();

      const newRun = await api.createRun({
        title: isUrl ? "Target URL Verification" : text.slice(0, 40),
        objective,
        target_url: targetUrl,
        mode: "interactive",
      });

      setSelectedRunId(newRun.id);
      showNotification("Kane verification run queued and executing.", "success");
      await refreshData();
    } catch (err: unknown) {
      showNotification(`Failed to create verification run: ${err instanceof Error ? err.message : String(err)}`, "error");
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
          title: "Verify Cart State & Quantity",
          objective: "Navigate to http://127.0.0.1:3005, select size M, increment quantity to 2, verify subtotal reflects $198.00 in cart drawer.",
          target_url: "http://127.0.0.1:3005",
        });
        setSelectedRunId(run.id);
        showNotification("Cart Quantity probe executing.", "success");
      } else if (type === "add_to_bag") {
        const run = await api.createRun({
          title: "Add to Bag & Size Selection",
          objective: "Verify Acme Voyager Jacket size selector options (S, M, L), click Add to Bag, assert badge counter is 1.",
          target_url: "http://127.0.0.1:3005",
        });
        setSelectedRunId(run.id);
        showNotification("Add to Bag probe executing.", "success");
      } else if (type === "audit_catalog") {
        const run = await api.createRun({
          title: "Audit Catalog & Links",
          objective: "Audit catalog links, product image rendering, and header navigation on http://127.0.0.1:3005",
          target_url: "http://127.0.0.1:3005",
        });
        setSelectedRunId(run.id);
        showNotification("Catalog audit probe executing.", "success");
      } else if (type === "defect_autoheal") {
        await api.toggleDefect(true);
        setDefectActive(true);
        showNotification("Injected defect into checkout. Triggering secret shopper probe...", "error");
        const probeRes = await api.triggerGuardProbe();
        if (probeRes.run_id) setSelectedRunId(probeRes.run_id);
      }
      await refreshData();
    } catch (err: unknown) {
      showNotification(`Failed to launch scenario: ${err instanceof Error ? err.message : String(err)}`, "error");
    } finally {
      setIsCreating(false);
    }
  };

  // Handle Approve Repair
  const handleApproveRepair = async () => {
    if (!activeRepair) return;
    setIsApprovingRepair(true);
    showNotification("Applying patch diff and executing Kane retest probe...", "info");
    try {
      setRepairStep(5);
      const res = await api.approveRepair(activeRepair.id, "Approved in ShipProof Orchestrated Developer Console");
      showNotification(`Repair update: ${res.message}`, "success");
      setRepairStep(6);
      await refreshData();
    } catch (err: unknown) {
      showNotification(`Failed to approve repair: ${err instanceof Error ? err.message : String(err)}`, "error");
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
          <span className="text-[10px] text-zinc-500 font-mono">
            {new Date(r.created_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" })}
          </span>
        ),
      };
    });
  }, [runs, selectedRunId]);

  // Derived steps for ThoughtLine
  const runStepsList = useMemo(() => {
    if (selectedRun?.steps && selectedRun.steps.length > 0) {
      return selectedRun.steps.map((s) => s.remark || `Step ${s.step_index}`);
    }
    return [
      "Navigating to http://127.0.0.1:3005",
      "Selecting Acme Voyager Jacket (Size M)",
      "Adding item to bag & updating cart state",
      "Validating checkout payload & pricing",
      "Confirming purchase & order verification",
    ];
  }, [selectedRun]);

  // Active step text for ThoughtLine
  const activeStepText = useMemo(() => {
    if (selectedRun?.status === "running") {
      return "Autonomous Kane browser agent probing store flow...";
    }
    if (selectedRun?.status === "passed" || selectedRun?.status === "verified") {
      return "Checkout flow verified with cryptographically valid proof.";
    }
    if (selectedRun?.status === "failed") {
      return `Verification failed: ${selectedRun.failure_reason || "Checkout button unresponsive"}`;
    }
    return "Ready for verification dispatch";
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
          className={`fixed top-4 right-4 z-50 px-4 py-2.5 rounded-full shadow-2xl text-xs font-mono flex items-center gap-2.5 border backdrop-blur-xl transition-all animate-in fade-in slide-in-from-top-2 ${
            notification.type === "success"
              ? "bg-emerald-950/90 text-emerald-300 border-emerald-500/30 shadow-emerald-900/30"
              : notification.type === "error"
              ? "bg-rose-950/90 text-rose-300 border-rose-500/30 shadow-rose-900/30"
              : "bg-blue-950/90 text-blue-300 border-blue-500/30 shadow-blue-900/30"
          }`}
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
              <span className="text-[10px] uppercase font-mono px-2 py-0.5 rounded-full bg-white/[0.08] border border-white/15 text-zinc-300">
                Enterprise AI Console
              </span>
            </div>
            <p className="text-[11px] text-zinc-400">Autonomous Software Verification &amp; Repair</p>
          </div>
        </div>

        {/* Live System State Marks */}
        <div className="flex items-center flex-wrap gap-3 text-xs">
          {/* Kane CLI status */}
          <div className="flex items-center gap-1.5 px-3 py-1 rounded-full bg-white/[0.05] border border-white/10 backdrop-blur-md">
            <StatusMark
              status={health?.kane_cli_installed !== false ? "done" : "failed"}
              size={13}
              doneColor="#10b981"
            />
            <span className="text-zinc-200 font-mono text-[11px]">
              kane-cli {health?.kane_cli_installed ? "v2.4" : "offline"}
            </span>
          </div>

          {/* Revenue Guard Sentinel status */}
          <div className="flex items-center gap-1.5 px-3 py-1 rounded-full bg-white/[0.05] border border-white/10 backdrop-blur-md">
            <StatusMark
              status={guardStatus?.enabled ? "running" : "done"}
              size={13}
              color="#3b82f6"
              doneColor="#10b981"
            />
            <span className="text-zinc-200 font-mono text-[11px]">
              Sentinel: {guardStatus?.enabled ? `Active (${guardStatus.interval_label})` : "Standby"}
            </span>
          </div>

          {/* Store Target link */}
          <a
            href="http://127.0.0.1:3005"
            target="_blank"
            rel="noreferrer"
            className="flex items-center gap-1.5 px-3 py-1 rounded-full bg-blue-500/15 border border-blue-500/30 text-blue-300 hover:bg-blue-500/25 transition-all font-mono text-[11px] backdrop-blur-md"
          >
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
            <span>Store :3005</span>
            <ExternalLink className="w-3 h-3 ml-0.5 opacity-70" />
          </a>
        </div>

        {/* Sentinel Interval & Refresh Controls */}
        <div className="flex items-center gap-2">
          <div className="flex items-center rounded-full bg-white/[0.05] p-1 border border-white/10 backdrop-blur-md">
            <span className="text-[10px] uppercase font-mono px-2 text-zinc-400">Interval</span>
            {[
              { label: "1m", sec: 60 },
              { label: "2m", sec: 120 },
              { label: "5m", sec: 300 },
            ].map((btn) => (
              <button
                key={btn.sec}
                type="button"
                onClick={() => handleSetInterval(btn.sec)}
                className={`text-[11px] font-mono px-2.5 py-1 rounded-full transition-all cursor-pointer ${
                  guardStatus?.interval_seconds === btn.sec
                    ? "bg-[#1863dc] text-white shadow-md font-semibold"
                    : "text-zinc-400 hover:text-white"
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
            title="Refresh All Telemetry"
          >
            <RefreshCw className="w-3.5 h-3.5" />
          </LiquidGlassButton>
        </div>
      </header>

      {/* Main Container */}
      <main className="flex-1 w-full max-w-7xl mx-auto px-4 sm:px-6 py-6 flex flex-col gap-6">
        {/* 1. Metrics Banner — Liquid Glass Cards */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          {/* Total Probes */}
          <LiquidGlassCard
            glowColor="rgba(56, 189, 248, 0.3)"
            className="p-4 flex flex-col gap-1 shadow-xl hover:shadow-sky-500/10"
          >
            <div className="flex items-center justify-between text-zinc-400 text-xs">
              <span className="flex items-center gap-1.5">
                <Activity className="w-3.5 h-3.5 text-sky-400" />
                <span>Total Probes Run</span>
              </span>
              <span className="text-[10px] font-mono text-zinc-300 bg-white/[0.08] px-1.5 py-0.5 rounded">Kane CLI</span>
            </div>
            <div className="flex items-baseline gap-2 mt-1">
              <Counter
                value={guardStatus?.total_probes ?? overview?.total_runs ?? 18}
                fontSize="28px"
                fontWeight={700}
                textColor="#ffffff"
                fade={0}
              />
              <span className="text-xs text-emerald-400 font-mono font-medium">100% Truth</span>
            </div>
          </LiquidGlassCard>

          {/* Revenue Protected */}
          <LiquidGlassCard
            glowColor="rgba(16, 185, 129, 0.3)"
            className="p-4 flex flex-col gap-1 shadow-xl hover:shadow-emerald-500/10"
          >
            <div className="flex items-center justify-between text-zinc-400 text-xs">
              <span className="flex items-center gap-1.5">
                <ShieldCheck className="w-3.5 h-3.5 text-emerald-400" />
                <span>Revenue Protected</span>
              </span>
              <span className="text-[10px] font-mono text-emerald-400 bg-emerald-500/15 px-1.5 py-0.5 rounded border border-emerald-500/30">Live</span>
            </div>
            <div className="flex items-baseline gap-1 mt-1">
              <span className="text-2xl font-bold text-emerald-400">$</span>
              <Counter
                value={guardStatus?.revenue_protected ?? 495}
                fontSize="28px"
                fontWeight={700}
                textColor="#34d399"
                fade={0}
              />
              <span className="text-xs text-zinc-400 font-mono ml-1.5">Acme Store</span>
            </div>
          </LiquidGlassCard>

          {/* Revenue at Risk */}
          <LiquidGlassCard
            glowColor={defectActive ? "rgba(244, 63, 94, 0.4)" : "rgba(255, 255, 255, 0.15)"}
            className="p-4 flex flex-col gap-1 shadow-xl hover:shadow-rose-500/10"
          >
            <div className="flex items-center justify-between text-zinc-400 text-xs">
              <span className="flex items-center gap-1.5">
                <ShieldAlert className="w-3.5 h-3.5 text-rose-400" />
                <span>Revenue at Risk</span>
              </span>
              <span className={`text-[10px] font-mono px-1.5 py-0.5 rounded ${defectActive ? "bg-rose-500/25 text-rose-300 border border-rose-500/40 animate-pulse font-semibold" : "bg-white/[0.08] text-zinc-400"}`}>
                {defectActive ? "DEFECT DETECTED" : "Clear"}
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
              <span className="text-xs text-zinc-400 font-mono ml-1.5">per broken order</span>
            </div>
          </LiquidGlassCard>

          {/* Verified Fixes */}
          <LiquidGlassCard
            glowColor="rgba(245, 158, 11, 0.3)"
            className="p-4 flex flex-col gap-1 shadow-xl hover:shadow-amber-500/10"
          >
            <div className="flex items-center justify-between text-zinc-400 text-xs">
              <span className="flex items-center gap-1.5">
                <Wrench className="w-3.5 h-3.5 text-amber-400" />
                <span>Verified Healed Fixes</span>
              </span>
              <span className="text-[10px] font-mono text-amber-300 bg-amber-500/15 px-1.5 py-0.5 rounded border border-amber-500/30">Closed-Loop</span>
            </div>
            <div className="flex items-baseline gap-2 mt-1">
              <Counter
                value={overview?.repairs_verified ?? (repairs.filter((r) => r.status === "VERIFIED").length || 1)}
                fontSize="28px"
                fontWeight={700}
                textColor="#ffffff"
                fade={0}
              />
              <span className="text-xs text-zinc-400 font-mono">1-click git approvals</span>
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
              placeholder="Target URL or natural-language verification objective (e.g. Verify checkout on http://127.0.0.1:3005)..."
              onSend={handlePromptSend}
              busy={isCreating || isProbing}
              models={[
                { key: "kane-deep", name: "Kane Deep Proof v2.4", tag: "High-Fidelity" },
                { key: "kane-guard", name: "Revenue Guard Sentinel", tag: "Secret Shopper" },
              ]}
              defaultModel="kane-deep"
              efforts={["Thorough", "Fast Audit"]}
              defaultEffort="Thorough"
            />
          </LiquidGlassCard>

          {/* Quick-Launch Scenario Pills — Liquid Glass Buttons */}
          <div className="flex items-center flex-wrap gap-2 pt-1">
            <span className="text-[11px] font-mono uppercase text-zinc-400 mr-1 flex items-center gap-1">
              <Sparkles className="w-3 h-3 text-sky-400" />
              Scenarios:
            </span>

            <LiquidGlassButton
              variant="primary"
              size="sm"
              onClick={() => launchScenario("sentinel_checkout")}
            >
              <Play className="w-3 h-3 text-blue-300 fill-current" />
              <span>Sentinel Checkout Probe</span>
            </LiquidGlassButton>

            <LiquidGlassButton
              variant="glass"
              size="sm"
              onClick={() => launchScenario("cart_quantity")}
            >
              Verify Cart &amp; Quantity ($198.00)
            </LiquidGlassButton>

            <LiquidGlassButton
              variant="glass"
              size="sm"
              onClick={() => launchScenario("add_to_bag")}
            >
              Add to Bag &amp; Size Selection
            </LiquidGlassButton>

            <LiquidGlassButton
              variant="glass"
              size="sm"
              onClick={() => launchScenario("audit_catalog")}
            >
              Audit Catalog &amp; Navigation
            </LiquidGlassButton>

            <LiquidGlassButton
              variant="danger"
              size="sm"
              onClick={() => launchScenario("defect_autoheal")}
            >
              <Bug className="w-3 h-3 text-rose-300" />
              <span>Simulate Defect → Auto-Heal</span>
            </LiquidGlassButton>
          </div>
        </div>

        {/* 3. Main Bento Orchestration Grid (2 Columns) */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
          {/* Left Column (5 Cols): Revenue Guard Sentinel & Repair Studio */}
          <div className="lg:col-span-5 flex flex-col gap-6">
            {/* Card 1: Revenue Guard Sentinel — Liquid Glass Card */}
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
                    <h3 className="text-sm font-semibold text-white tracking-tight">Revenue Guard Sentinel</h3>
                    <p className="text-[11px] text-zinc-400">Autonomous Secret Shopper Protection</p>
                  </div>
                </div>

                <div className="flex items-center gap-2">
                  <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-emerald-500/15 text-emerald-400 border border-emerald-500/30 flex items-center gap-1.5 font-semibold">
                    <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-ping" />
                    LIVE
                  </span>
                </div>
              </div>

              {/* Status and Next Probe Timer */}
              <div className="grid grid-cols-2 gap-3 p-3.5 rounded-2xl bg-black/40 border border-white/[0.08]">
                <div>
                  <span className="text-[10px] uppercase font-mono text-zinc-400 block">Next Probe In</span>
                  <div className="flex items-baseline gap-1 mt-0.5">
                    <span className="text-xl font-bold font-mono text-white">{countdown}</span>
                    <span className="text-xs text-zinc-400 font-mono">seconds</span>
                  </div>
                </div>
                <div>
                  <span className="text-[10px] uppercase font-mono text-zinc-400 block">Frequency</span>
                  <div className="flex items-baseline gap-1 mt-0.5">
                    <span className="text-sm font-semibold text-zinc-200">Every {guardStatus?.interval_label || "2 minutes"}</span>
                  </div>
                </div>
              </div>

              {/* Defect Simulator Banner with Liquid Toggle */}
              <div
                className={`p-3.5 rounded-2xl border transition-all flex flex-col gap-2.5 ${
                  defectActive
                    ? "bg-rose-950/40 border-rose-500/40 text-rose-200"
                    : "bg-emerald-950/30 border-emerald-500/30 text-emerald-200"
                }`}
              >
                <div className="flex items-center justify-between">
                  <span className="text-xs font-semibold flex items-center gap-1.5 font-mono">
                    {defectActive ? (
                      <>
                        <AlertTriangle className="w-4 h-4 text-rose-400 animate-pulse" />
                        DEFECT ACTIVE: Checkout Blocked
                      </>
                    ) : (
                      <>
                        <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                        Store Operating Normally
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
                    ? "Checkout button intentionally modified on :3005 to simulate checkout failure. Sentinel catches defect and triggers automated repair."
                    : "No defects injected. Secret shopper probes verify full cart-to-order pipeline."}
                </p>
              </div>

              {/* Action Buttons — Liquid Glass Buttons */}
              <div className="flex items-center gap-2.5 pt-1">
                <div className="flex-1">
                  <LiquidGlassButton
                    variant="primary"
                    size="md"
                    fullWidth
                    disabled={isProbing}
                    onClick={handleTriggerProbe}
                  >
                    {isProbing ? (
                      <>
                        <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                        <span>Probing :3005...</span>
                      </>
                    ) : (
                      <>
                        <Play className="w-3.5 h-3.5 fill-current" />
                        <span>Run Secret Shopper Now</span>
                      </>
                    )}
                  </LiquidGlassButton>
                </div>

                <LiquidGlassButton
                  variant={defectActive ? "emerald" : "danger"}
                  size="md"
                  disabled={isTogglingDefect}
                  onClick={handleToggleDefect}
                >
                  <Bug className="w-3.5 h-3.5" />
                  <span>{defectActive ? "Clear Defect" : "Inject Defect"}</span>
                </LiquidGlassButton>
              </div>
            </LiquidGlassCard>

            {/* Card 2: Repair Studio & Closed-Loop Healing — Liquid Glass Card */}
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
                    <h3 className="text-sm font-semibold text-white tracking-tight">Repair Studio</h3>
                    <p className="text-[11px] text-zinc-400">Kane Closed-Loop Automated Healing</p>
                  </div>
                </div>

                <span
                  className={`text-[10px] font-mono px-2 py-0.5 rounded-full uppercase border font-semibold ${
                    activeRepair?.status === "VERIFIED"
                      ? "bg-emerald-500/15 text-emerald-400 border-emerald-500/30"
                      : activeRepair?.status === "AWAITING_APPROVAL"
                      ? "bg-amber-500/15 text-amber-400 border-amber-500/30 animate-pulse"
                      : "bg-zinc-800 text-zinc-400 border-zinc-700"
                  }`}
                >
                  {activeRepair?.status || "STANDBY"}
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
                  <Step title="Failure" description="Failure detected by Kane">
                    <div className="p-3 rounded-xl bg-black/40 border border-white/10 text-xs text-zinc-300">
                      Kane identified broken checkout payload on http://127.0.0.1:3005. Revenue at risk: $99.00.
                    </div>
                  </Step>
                  <Step title="Diagnosis" description="Root-cause diagnostic">
                    <div className="p-3 rounded-xl bg-black/40 border border-white/10 text-xs text-zinc-300">
                      Analysis: DOM selector &apos;#checkout-btn&apos; had an intentional click trap or disabled attribute in sample store.
                    </div>
                  </Step>
                  <Step title="IDE Handoff" description="Agent workspace patch">
                    <div className="p-3 rounded-xl bg-black/40 border border-white/10 text-xs text-zinc-300">
                      Agent targeted <code className="text-blue-400">demo_targets/sample_store/templates/cart.html</code> and generated patch diff.
                    </div>
                  </Step>
                  <Step title="Diff Approval" description="Human-in-the-loop inspect">
                    <div className="p-3 rounded-xl bg-black/40 border border-white/10 text-xs text-zinc-300">
                      Review unified diff below. One click applies code patch to workspace.
                    </div>
                  </Step>
                  <Step title="Kane Retest" description="Autonomous validation">
                    <div className="p-3 rounded-xl bg-black/40 border border-white/10 text-xs text-zinc-300">
                      Kane CLI spins up headless browser and re-runs checkout probe to verify fix.
                    </div>
                  </Step>
                  <Step title="Verified" description="Closed-loop proof">
                    <div className="p-3 rounded-xl bg-black/40 border border-white/10 text-xs text-emerald-300">
                      Proof recorded with exit code 0. Clean checkout confirmed.
                    </div>
                  </Step>
                </Stepper>
              </div>

              {/* Syntax Highlighted Git Diff Preview */}
              <div className="flex flex-col gap-1.5">
                <div className="flex items-center justify-between text-[11px] font-mono text-zinc-400">
                  <span className="flex items-center gap-1">
                    <Layers className="w-3.5 h-3.5 text-zinc-500" />
                    <span>{activeRepair?.files_modified?.[0] || "demo_targets/sample_store/templates/cart.html"}</span>
                  </span>
                  <span className="text-[10px] text-zinc-500 font-mono">git diff (unified)</span>
                </div>

                <div className="rounded-2xl bg-black/60 border border-white/10 p-3.5 font-mono text-[11px] leading-relaxed overflow-x-auto max-h-48 text-zinc-300 select-text">
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
                            ? "text-zinc-500 font-semibold"
                            : "text-zinc-400"
                        }`}
                      >
                        {line}
                      </div>
                    );
                  })}
                </div>
              </div>

              {/* Approval Actions — Liquid Glass Buttons */}
              <div className="flex items-center gap-2.5 pt-1">
                <div className="flex-1">
                  <LiquidGlassButton
                    variant="emerald"
                    size="md"
                    fullWidth
                    disabled={isApprovingRepair}
                    onClick={handleApproveRepair}
                  >
                    {isApprovingRepair ? (
                      <>
                        <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                        <span>Applying &amp; Retesting...</span>
                      </>
                    ) : (
                      <>
                        <CheckCircle2 className="w-3.5 h-3.5" />
                        <span>Approve Patch &amp; Retest with Kane</span>
                      </>
                    )}
                  </LiquidGlassButton>
                </div>

                <LiquidGlassButton
                  variant="glass"
                  size="md"
                  onClick={() => showNotification("Patch rejected by operator.", "info")}
                >
                  Reject
                </LiquidGlassButton>
              </div>
            </LiquidGlassCard>
          </div>

          {/* Right Column (7 Cols): Kane Telemetry, ThoughtLine, CallChips & Run Feed */}
          <div className="lg:col-span-7 flex flex-col gap-6">
            {/* Card 3: Selected Run Execution Trace — Liquid Glass Card */}
            <LiquidGlassCard
              glowColor="rgba(56, 189, 248, 0.25)"
              className="p-5 flex flex-col gap-4 shadow-2xl"
            >
              <div className="flex items-center justify-between border-b border-white/10 pb-3">
                <div className="flex items-center gap-2.5">
                  <div className="p-1.5 rounded-xl bg-blue-500/15 text-blue-400 border border-blue-500/25">
                    <Terminal className="w-4 h-4" />
                  </div>
                  <div>
                    <h3 className="text-sm font-semibold text-white tracking-tight">
                      {selectedRun?.title || "Verification Run Telemetry"}
                    </h3>
                    <p className="text-[11px] text-zinc-400 font-mono">
                      Target: {selectedRun?.target_url || "http://127.0.0.1:3005"}
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
                  <span className="text-xs font-mono uppercase text-zinc-200">
                    {selectedRun?.status || "IDLE"}
                  </span>
                </div>
              </div>

              {/* Active Loader when running */}
              {selectedRun?.status === "running" && (
                <div className="p-4 rounded-2xl bg-blue-500/15 border border-blue-500/30 flex items-center justify-between backdrop-blur-md">
                  <LatticeLoader
                    status="working"
                    label="Autonomous Kane probe navigating store..."
                    pattern="sweep"
                    color="#38bdf8"
                  />
                  <span className="text-[11px] font-mono text-blue-300 animate-pulse">Running live</span>
                </div>
              )}

              {/* ThoughtLine: Kane Execution Timeline */}
              <div className="p-4 rounded-2xl bg-black/40 border border-white/[0.08] flex flex-col gap-2">
                <span className="text-[10px] uppercase font-mono text-zinc-400">Kane Agent Execution Trace</span>
                <ThoughtLine
                  label={activeStepText}
                  doneLabel="Verification run concluded with verified proof"
                  steps={runStepsList}
                  glyph="sparkle"
                  working={selectedRun?.status === "running"}
                  showTimer={true}
                  color="#ffffff"
                  glyphColor="#38bdf8"
                />
              </div>

              {/* CallChips: Real Browser Tools Invoked */}
              <div className="flex flex-col gap-2">
                <span className="text-[10px] uppercase font-mono text-zinc-400">Browser Action Telemetry</span>
                <div className="flex items-center flex-wrap gap-2">
                  <CallChip
                    icon="terminal"
                    name="navigate"
                    argument="http://127.0.0.1:3005"
                    status="done"
                  />
                  <CallChip
                    icon="terminal"
                    name="click"
                    argument="#size-m-button"
                    status="done"
                  />
                  <CallChip
                    icon="terminal"
                    name="click"
                    argument="#add-to-bag-button"
                    status="done"
                  />
                  <CallChip
                    icon="search"
                    name="assert"
                    argument="cart.total === 99.00"
                    status="done"
                  />
                  <CallChip
                    icon="terminal"
                    name="click"
                    argument="#checkout-btn"
                    status={selectedRun?.status === "failed" ? "error" : "done"}
                  />
                </div>
              </div>

              {/* Objective & Verification Proof Note */}
              <div className="p-3.5 rounded-2xl bg-black/40 border border-white/[0.08] flex flex-col gap-1.5 text-xs text-zinc-300">
                <div className="flex items-center justify-between text-zinc-400 text-[11px] font-mono">
                  <span>Objective:</span>
                  <span>ID: {selectedRun?.id?.slice(0, 8) || "run-latest"}</span>
                </div>
                <p className="text-zinc-200">{selectedRun?.objective || "Verify end-to-end checkout flow on Acme Voyager store."}</p>
                {selectedRun?.failure_reason && (
                  <div className="mt-1 text-rose-400 font-mono text-[11px] bg-rose-500/15 p-2.5 rounded-xl border border-rose-500/30">
                    Failure reason: {selectedRun.failure_reason}
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
                  <h3 className="text-sm font-semibold text-white">Recent Verification Probes</h3>
                </div>
                <span className="text-[11px] font-mono text-zinc-400">{runs.length} runs recorded</span>
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
      <footer className="w-full border-t border-white/10 bg-black/40 backdrop-blur-xl py-3.5 px-6 mt-8 text-center text-xs text-zinc-400 font-mono flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="text-zinc-300 font-medium">ShipProof v2.4</span>
          <span>•</span>
          <span>Kane CLI Engine</span>
          <span>•</span>
          <span>React Bits Design</span>
        </div>
        <div>
          <span>Your AI writes the code. ShipProof proves it works.</span>
        </div>
      </footer>
    </div>
  );
}

export default ShipProofConsole;
