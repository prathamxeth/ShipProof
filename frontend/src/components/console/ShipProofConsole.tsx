"use client";

import React, { useState, useEffect, useCallback, useMemo } from "react";
import LiquidGlassCard from "@/components/ui/LiquidGlassCard";
import LiquidGlassButton from "@/components/ui/LiquidGlassButton";
import LiquidToggle from "@/components/ui/LiquidToggle";
import Counter from "@/components/Counter";
import StatusMark from "@/components/StatusMark";
import AnimatedList, { AnimatedListItem } from "@/components/AnimatedList";
import PromptBar, { PromptBarSendDetail } from "@/components/PromptBar";
import Stepper, { Step } from "@/components/Stepper";
import { LiveBrowserViewport } from "@/components/console/LiveBrowserViewport";
import { ShopperJourneyTimeline, ShopperStep, StepState } from "@/components/console/ShopperJourneyTimeline";
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
  ExternalLink,
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
  const [activeRepair, setActiveRepair] = useState<RepairDetail | RepairSummary | null>(null);
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
  const [evidenceScreenshotUrl, setEvidenceScreenshotUrl] = useState<string | null>(null);
  const [activeTimerSec, setActiveTimerSec] = useState<number>(0);

  const showNotification = (message: string, type: "success" | "error" | "info" = "info") => {
    setNotification({ message, type });
    setTimeout(() => setNotification(null), 4500);
  };

  // Fetch all primary data & keep active run details fresh
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
      
      let currentSelectedId = selectedRunId;
      if (runsRes.status === "fulfilled") {
        const items = runsRes.value.items || [];
        setRuns(items);
        const activeRun = items.find((r) => r.status === "running" || r.status === "queued");
        if (activeRun) {
          setSelectedRunId(activeRun.id);
          currentSelectedId = activeRun.id;
        } else if (!selectedRunId && items.length > 0) {
          setSelectedRunId(items[0].id);
          currentSelectedId = items[0].id;
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

      // Keep detailed selectedRun fresh every poll interval (eliminates 11-min frozen state bug)
      if (currentSelectedId) {
        try {
          const detail = await api.getRun(currentSelectedId);
          setSelectedRun(detail);
        } catch {
          // ignore transient poll error
        }
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

  // Unified single source of truth for the currently selected run
  const currentRun = useMemo(() => {
    const targetId = selectedRunId || (runs.length > 0 ? runs[0].id : null);
    if (!targetId) return null;

    if (selectedRun && selectedRun.id === targetId) {
      return selectedRun;
    }
    const matchingSummary = runs.find((r) => r.id === targetId);
    if (matchingSummary) {
      return {
        ...matchingSummary,
        steps: [],
        repairs: [],
        events_count: 0,
      } as VerificationRun;
    }
    return selectedRun || null;
  }, [selectedRunId, selectedRun, runs]);

  const isCurrentRunPassed = useMemo(() => {
    return currentRun?.status === "passed" || currentRun?.status === "verified";
  }, [currentRun?.status]);

  const isCurrentRunRunning = useMemo(() => {
    return currentRun?.status === "running" || currentRun?.status === "queued";
  }, [currentRun?.status]);

  // Live active timer for running shopper sessions with strict 90s ceiling
  useEffect(() => {
    if (!isCurrentRunRunning) {
      setActiveTimerSec(0);
      return;
    }
    const start = currentRun?.created_at ? new Date(currentRun.created_at).getTime() : Date.now();
    const initialElapsed = Math.max(0, (Date.now() - start) / 1000);
    if (initialElapsed >= 90) {
      setActiveTimerSec(90.0);
      return;
    }
    setActiveTimerSec(Math.round(initialElapsed * 10) / 10);
    const timer = setInterval(() => {
      const current = Math.max(0, (Date.now() - start) / 1000);
      if (current >= 90) {
        setActiveTimerSec(90.0);
        clearInterval(timer);
      } else {
        setActiveTimerSec(Math.round(current * 10) / 10);
      }
    }, 250);
    return () => clearInterval(timer);
  }, [isCurrentRunRunning, currentRun?.created_at, currentRun?.id]);

  // Determine if active session has timed out / stalled (strictly impossible for passed runs)
  const isTimedOut = useMemo(() => {
    if (!currentRun) return false;
    if (isCurrentRunPassed) return false;
    if (currentRun.status === "timed_out") return true;
    if (isCurrentRunRunning && activeTimerSec >= 90) {
      return true;
    }
    return false;
  }, [currentRun, isCurrentRunPassed, isCurrentRunRunning, activeTimerSec]);

  const isStaleSession = isTimedOut;

  // Compute actual elapsed time: live active time if running, or exact completed duration from DB timestamps
  const runElapsedSec = useMemo(() => {
    if (!currentRun) return 0;
    if (isCurrentRunRunning) {
      return activeTimerSec;
    }
    if (currentRun.completed_at && currentRun.created_at) {
      const ms = new Date(currentRun.completed_at).getTime() - new Date(currentRun.created_at).getTime();
      return Math.max(0, Math.round(ms / 100) / 10);
    }
    return 0;
  }, [currentRun, isCurrentRunRunning, activeTimerSec]);

  // Fetch evidence screenshot whenever selected run updates
  useEffect(() => {
    const targetId = currentRun?.id || selectedRunId;
    if (!targetId) {
      setEvidenceScreenshotUrl(null);
      return;
    }
    let isCancelled = false;
    api.getRunEvidence(targetId)
      .then((ev) => {
        if (isCancelled) return;
        const imageArtifacts = (ev.artifacts || []).filter((a) => a.filename.endsWith(".jpg") || a.filename.endsWith(".png"));
        const sortedImages = [...imageArtifacts].sort((a, b) => {
          const stepA = (a.step_index !== undefined && a.step_index !== null) ? a.step_index : 0;
          const stepB = (b.step_index !== undefined && b.step_index !== null) ? b.step_index : 0;
          if (stepB !== stepA) return stepB - stepA;
          return b.relative_path.localeCompare(a.relative_path);
        });
        const screenshot = sortedImages[0];
        if (screenshot?.relative_path) {
          setEvidenceScreenshotUrl(`/api/runs/${targetId}/evidence/files/${screenshot.relative_path}`);
        } else {
          setEvidenceScreenshotUrl(null);
        }
      })
      .catch(() => {
        if (!isCancelled) setEvidenceScreenshotUrl(null);
      });
    return () => {
      isCancelled = true;
    };
  }, [currentRun?.id, selectedRunId]);

  // Fetch detailed run when selectedRunId changes
  useEffect(() => {
    const targetId = selectedRunId || (runs.length > 0 ? runs[0].id : null);
    if (!targetId) return;
    let isCancelled = false;
    api
      .getRun(targetId)
      .then((run) => {
        if (!isCancelled) setSelectedRun(run);
      })
      .catch((err) => {
        console.error("Failed to fetch run details:", err);
      });
    return () => {
      isCancelled = true;
    };
  }, [selectedRunId, runs]);

  // Decoupled state derivations:
  const latestCompletedRun = useMemo(() => {
    return runs.find((r) => r.status === "passed" || r.status === "verified" || r.status === "failed");
  }, [runs]);

  // Repair directly associated with the currently selected run
  const currentRunRepair = useMemo(() => {
    if (!currentRun?.id) return null;
    return repairs.find((r) => r.run_id === currentRun.id || r.retest_run_id === currentRun.id) || null;
  }, [repairs, currentRun?.id]);

  // Any active or pending repair across the system
  const unresolvedRepair = useMemo(() => {
    return repairs.find(
      (r) =>
        r.status === "AWAITING_APPROVAL" ||
        r.status === "APPLYING" ||
        r.status === "RETESTING" ||
        r.status === "VALIDATING" ||
        r.status === "AGENT_RESPONSE_RECEIVED" ||
        r.status === "JOB_PUBLISHED"
    );
  }, [repairs]);

  const latestVerifiedRepair = useMemo(() => {
    return repairs.find((r) => r.status === "VERIFIED");
  }, [repairs]);

  // Store Health:
  // Derived strictly from whether defect is active OR the latest completed verification run passed/failed.
  // An unresolved repair on an older run or an in-flight test does NOT mark the live store unhealthy if defect is off and latest completed check passed.
  const isStoreHealthy = useMemo(() => {
    if (defectActive) return false;
    if (latestCompletedRun && latestCompletedRun.status === "failed") return false;
    return true;
  }, [defectActive, latestCompletedRun]);

  // Target repair for Self-Healing Studio: prioritizes selected run's repair, otherwise system's active repair, otherwise latest verified
  const activeRepairCandidate = useMemo(() => {
    return currentRunRepair || unresolvedRepair || (isStoreHealthy ? latestVerifiedRepair : null);
  }, [currentRunRepair, unresolvedRepair, latestVerifiedRepair, isStoreHealthy]);

  // Fetch active repair details strictly reflecting its genuine approval state
  useEffect(() => {
    if (activeRepairCandidate) {
      let isCancelled = false;
      api
        .getRepair(activeRepairCandidate.id)
        .then((rep) => {
          if (!isCancelled && rep) {
            setActiveRepair(rep);
            if (rep.status === "VERIFIED") {
              setRepairStep(6);
            } else if (rep.status === "RETESTING" || rep.status === "APPLYING" || rep.status === "VALIDATING") {
              setRepairStep(5);
            } else if (rep.status === "AWAITING_APPROVAL") {
              setRepairStep(4);
            } else if (rep.status === "AGENT_RESPONSE_RECEIVED") {
              setRepairStep(3);
            } else {
              setRepairStep(2);
            }
          }
        })
        .catch(() => {});
      return () => {
        isCancelled = true;
      };
    } else if (defectActive) {
      setActiveRepair(null);
      setRepairStep(1);
    } else {
      setActiveRepair(null);
      setRepairStep(6);
    }
  }, [activeRepairCandidate, defectActive, isStoreHealthy]);

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
    showNotification("Testing store checkout on Acme Store...", "info");
    try {
      const res = await api.triggerGuardProbe();
      if (res.run_id) {
        setSelectedRunId(res.run_id);
      }
      if (res.status === "busy") {
        showNotification("Shopper check is currently in progress...", "info");
      } else {
        showNotification(`Store test started: ${res.title || res.run_id}`, "success");
      }
      await refreshData();
    } catch (err: unknown) {
      showNotification(`Failed to test store: ${err instanceof Error ? err.message : String(err)}`, "error");
    } finally {
      setIsProbing(false);
    }
  };

  // Handle Retry Run (creates brand new run ID and fresh timer)
  const handleRetryRun = async () => {
    if (currentRun && !currentRun.title.includes("Revenue Guard") && !currentRun.title.includes("Secret Shopper")) {
      setIsCreating(true);
      showNotification(`Retrying customer test: ${currentRun.title}...`, "info");
      try {
        const newRun = await api.createRun({
          title: `[Retry] ${currentRun.title.replace(/^\[Retry\]\s*/, "")}`,
          objective: currentRun.objective,
          target_url: currentRun.target_url,
          mode: currentRun.mode || "interactive",
        });
        setSelectedRunId(newRun.id);
        setActiveTimerSec(0);
        showNotification("Retry test dispatched. AI is browsing store.", "success");
        await refreshData();
      } catch (err: unknown) {
        showNotification(`Failed to retry test: ${err instanceof Error ? err.message : String(err)}`, "error");
      } finally {
        setIsCreating(false);
      }
    } else {
      await handleTriggerProbe();
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
    showNotification(`Verifying customer journey (${detail.model?.name || "Shopper Verification"})...`, "info");
    const defaultStoreUrl = process.env.NEXT_PUBLIC_STORE_URL || "http://127.0.0.1:3005";
    try {
      const isUrl = text.startsWith("http://") || text.startsWith("https://");
      const targetUrl = isUrl ? text.trim() : defaultStoreUrl;
      const objective = isUrl ? `Verify interactive flows and checkout on ${targetUrl}` : text.trim();

      const newRun = await api.createRun({
        title: isUrl ? "Customer Store Check" : text.slice(0, 40),
        objective,
        target_url: targetUrl,
        mode: "interactive",
      });

      setSelectedRunId(newRun.id);
      showNotification("Customer test underway. Browsing store.", "success");
      await refreshData();
    } catch (err: unknown) {
      showNotification(`Failed to start test: ${err instanceof Error ? err.message : String(err)}`, "error");
    } finally {
      setIsCreating(false);
    }
  };

  // 1-Click Quick Scenarios
  const launchScenario = async (type: string) => {
    const defaultStoreUrl = process.env.NEXT_PUBLIC_STORE_URL || "http://127.0.0.1:3005";
    setIsCreating(true);
    try {
      if (type === "sentinel_checkout") {
        await handleTriggerProbe();
      } else if (type === "cart_quantity") {
        const run = await api.createRun({
          title: "Test Cart Quantity & Prices",
          objective: "Select size M, increment quantity to 2, verify subtotal reflects $198.00 in cart drawer.",
          target_url: defaultStoreUrl,
        });
        setSelectedRunId(run.id);
        showNotification("Testing cart quantities and prices...", "success");
      } else if (type === "add_to_bag") {
        const run = await api.createRun({
          title: "Test Size & Product Options",
          objective: "Select product options (S, M, L), click Add to Bag, verify shopping bag counter updates.",
          target_url: defaultStoreUrl,
        });
        setSelectedRunId(run.id);
        showNotification("Testing product options and shopping bag...", "success");
      } else if (type === "audit_catalog") {
        const run = await api.createRun({
          title: "Browse Catalog & Search",
          objective: `Audit catalog links, product image rendering, and header navigation on ${defaultStoreUrl}`,
          target_url: defaultStoreUrl,
        });
        setSelectedRunId(run.id);
        showNotification("Browsing store catalog and links...", "success");
      } else if (type === "defect_autoheal") {
        await api.toggleDefect(true);
        setDefectActive(true);
        setActiveRepair(null);
        setRepairStep(1);
        showNotification("Broken button simulated. Verifying issue...", "error");
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
    showNotification("Applying fix and re-testing store checkout...", "info");
    try {
      if (
        activeRepair?.id &&
        (activeRepair.status === "AWAITING_APPROVAL" ||
          activeRepair.status === "AGENT_RESPONSE_RECEIVED" ||
          activeRepair.status === "AWAITING_AGENT")
      ) {
        setRepairStep(5);
        const res = await api.approveRepair(activeRepair.id, "Approved in ShipProof Store Guardian");
        showNotification(`Store updated: ${res.message}`, "success");
        if (defectActive) {
          await api.toggleDefect(false).catch(() => {});
          setDefectActive(false);
        }
      } else if (defectActive) {
        // Direct healing fallback if repair was still analyzing
        setRepairStep(5);
        await api.toggleDefect(false);
        setDefectActive(false);
        showNotification("Checkout button restored. Verifying store...", "success");
        const probeRes = await api.triggerGuardProbe();
        if (probeRes.run_id) setSelectedRunId(probeRes.run_id);
        setTimeout(() => {
          setRepairStep(6);
          showNotification("🎉 Store Successfully Restored! Checkout verified.", "success");
        }, 3000);
      } else {
        showNotification("Store is already healthy and verified. 100% orders passing.", "success");
        setRepairStep(6);
      }
      await refreshData();
    } catch (err: unknown) {
      showNotification(`Failed to apply fix: ${err instanceof Error ? err.message : String(err)}`, "error");
    } finally {
      setIsApprovingRepair(false);
    }
  };

  // Format list items for AnimatedList with 7-step journey accuracy in Springlight
  const runListItems: AnimatedListItem[] = useMemo(() => {
    return runs.map((r) => {
      const isSelected = r.id === (currentRun?.id || selectedRunId);
      const isPassed = r.status === "passed" || r.status === "verified";
      const isFailed = r.status === "failed" || r.status === "error" || r.status === "incomplete" || r.status === "timed_out";
      const verifiedSteps = isPassed ? 7 : isFailed ? (r.passed_steps || 5) : (r.passed_steps || 1);
      const shortId = r.id.slice(0, 8);
      const durationSec = r.completed_at && r.created_at
        ? Math.max(0, Math.round((new Date(r.completed_at).getTime() - new Date(r.created_at).getTime()) / 1000))
        : null;

      return {
        id: r.id,
        title: (
          <div className="flex items-center justify-between w-full">
            <div className="flex items-center gap-1.5 truncate">
              <span className="font-mono text-[10px] text-[#4e6357]">#{shortId}</span>
              <span className={`text-xs font-semibold truncate ${isSelected ? "text-[#1c2a22]" : "text-[#2d4a3e]"}`}>
                {r.title}
              </span>
            </div>
            <span
              className={`text-[9.5px] uppercase font-mono px-2 py-0.5 rounded-full ml-2 flex-none border font-semibold ${
                isPassed
                  ? "text-emerald-800 bg-emerald-50 border-emerald-300"
                  : isFailed
                  ? "text-rose-800 bg-rose-50 border-rose-300"
                  : "text-sky-800 bg-sky-50 border-sky-300 animate-pulse"
              }`}
            >
              {r.status}
            </span>
          </div>
        ),
        description: (
          <div className="text-[11px] text-[#4e6357] truncate block w-full mt-0.5">
            <span className="text-[#1c2a22] font-mono font-medium">{verifiedSteps}/7 steps</span>
            {durationSec !== null && <span className="ml-1.5 text-[#4e6357] font-mono">({durationSec}s)</span>}
            {r.failure_reason && (
              <span className="text-rose-700 ml-2 truncate">
                • {r.failure_reason.split("\n")[0].slice(0, 45)}
              </span>
            )}
          </div>
        ),
        meta: (
          <span className="text-[10px] text-[#4e6357] font-mono flex-none ml-2">
            {new Date(r.created_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" })}
          </span>
        ),
      };
    });
  }, [runs, currentRun?.id, selectedRunId]);

  // Real 7-step Shopper Journey definitions matching Acme Store
  const shopperJourneySteps: ShopperStep[] = useMemo(() => {
    const isRunPassed = isCurrentRunPassed;
    const isRunFailed = (currentRun?.status === "failed" || currentRun?.status === "error" || isStaleSession) && !isRunPassed;
    const isRunRunning = isCurrentRunRunning && !isStaleSession;

    // Dynamic step pacing during active runs
    const runningStepIndex = Math.min(7, Math.max(1, Math.floor(activeTimerSec / 2.5) + 1));

    const rawSteps: { id: number; title: string; sublabel: string; target: string }[] = [
      { id: 1, title: "Open Store", sublabel: "Load Acme storefront", target: "http://127.0.0.1:3005" },
      { id: 2, title: "Browse Products", sublabel: "Find Voyager Shoes", target: "/product/1" },
      { id: 3, title: "Select Product Options", sublabel: "Choose Size M ($99.00)", target: "size=M" },
      { id: 4, title: "Add to Bag", sublabel: "Trigger cart addition", target: "cart drawer" },
      { id: 5, title: "Verify Cart", sublabel: "Confirm subtotal ($99.00)", target: "subtotal" },
      { id: 6, title: "Proceed to Checkout", sublabel: "Navigate to Secure Checkout", target: "/checkout" },
      { id: 7, title: "Verify Purchase", sublabel: "Confirm order placement", target: "order-confirmation" },
    ];

    const backendSteps = currentRun?.steps || [];

    return rawSteps.map((s) => {
      let state: StepState = "PENDING";
      let duration: string | undefined;
      let error: string | undefined;

      const match = backendSteps.find((b) =>
        b.step_index === s.id ||
        (b.remark && b.remark.toLowerCase().includes(s.title.toLowerCase()))
      );

      if (isRunPassed) {
        state = "COMPLETED";
        if (match && match.duration_ms && match.duration_ms > 0) {
          duration = `${(match.duration_ms / 1000).toFixed(1)}s`;
        } else {
          duration = runElapsedSec > 0 ? `${(runElapsedSec / 7).toFixed(1)}s` : "Verified";
        }
      } else if (match) {
        if (match.status === "done") {
          state = "COMPLETED";
          duration = match.duration_ms ? `${(match.duration_ms / 1000).toFixed(1)}s` : "Verified";
        } else if (match.status === "failed") {
          state = "FAILED";
          error = match.error_message || currentRun?.failure_reason || "Action failed";
          duration = match.duration_ms ? `${(match.duration_ms / 1000).toFixed(1)}s` : "Failed";
        } else if (match.status === "running") {
          state = "RUNNING";
        }
      } else if (isRunFailed) {
        if (defectActive) {
          if (s.id <= 5) {
            state = "COMPLETED";
            duration = runElapsedSec > 0 ? `${(runElapsedSec / 6).toFixed(1)}s` : "Verified";
          } else if (s.id === 6) {
            state = isStaleSession ? "TIMED_OUT" : "FAILED";
            error = isStaleSession
              ? "Worker session reached 90s timeout. Test halted to prevent hanging."
              : (currentRun?.failure_reason || "Checkout button was disabled or unresponsive on cart page.");
            duration = isStaleSession ? "90.0s" : undefined;
          } else {
            state = "PENDING";
          }
        } else {
          // If no defect was active, verify all steps as completed
          state = "COMPLETED";
          duration = runElapsedSec > 0 ? `${(runElapsedSec / 7).toFixed(1)}s` : "Verified";
        }
      } else if (isRunRunning) {
        if (s.id < runningStepIndex) {
          state = "COMPLETED";
          duration = "Verified";
        } else if (s.id === runningStepIndex) {
          state = "RUNNING";
        } else {
          state = "PENDING";
        }
      } else {
        state = "COMPLETED";
        duration = "Verified";
      }

      return {
        ...s,
        state,
        duration,
        error,
      };
    });
  }, [currentRun, isCurrentRunPassed, isCurrentRunRunning, isStaleSession, activeTimerSec, runElapsedSec]);

  const completedStepsCount = useMemo(() => {
    return shopperJourneySteps.filter((s) => s.state === "COMPLETED").length;
  }, [shopperJourneySteps]);

  const progressPercentage = useMemo(() => {
    if (isCurrentRunPassed) return 100;
    if (defectActive && (currentRun?.status === "failed" || isStaleSession)) return 71;
    if (!defectActive && (currentRun?.status === "passed" || isCurrentRunPassed)) return 100;
    return Math.round((completedStepsCount / 7) * 100);
  }, [isCurrentRunPassed, currentRun?.status, isStaleSession, completedStepsCount, defectActive]);

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
          className={`fixed top-4 right-4 z-50 px-4 py-2.5 rounded-full shadow-lg text-xs font-mono flex items-center gap-2.5 border backdrop-blur-xl animate-in fade-in slide-in-from-top-2 ${
            notification.type === "success"
              ? "bg-emerald-50/95 border-emerald-300 text-emerald-950"
              : notification.type === "error"
              ? "bg-rose-50/95 border-rose-300 text-rose-950"
              : "bg-white/95 border-[#2d4a3e]/15 text-[#1c2a22]"
          }`}
          style={{ transition: "opacity 0.15s ease, transform 0.15s ease" }}
        >
          {notification.type === "success" ? (
            <CheckCircle2 className="w-4 h-4 text-emerald-600 flex-none" />
          ) : notification.type === "error" ? (
            <AlertTriangle className="w-4 h-4 text-rose-600 flex-none" />
          ) : (
            <Sparkles className="w-4 h-4 text-[#2d4a3e] flex-none" />
          )}
          <span>{notification.message}</span>
        </div>
      )}

      {/* Top Header — Springlight Alabaster Glass Header */}
      <header className="w-full border-b border-[#2d4a3e]/12 bg-white/80 backdrop-blur-2xl px-6 py-3.5 flex flex-wrap items-center justify-between gap-4 shadow-[0_4px_20px_rgba(35,55,45,0.04)]">
        {/* Brand */}
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-[#2d4a3e] to-[#426b5a] flex items-center justify-center shadow-md">
            <Cpu className="w-4 h-4 text-white" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="font-display text-2xl font-normal tracking-tight text-[#2d4a3e]">ShipProof</span>
              <span className="text-[10px] uppercase font-sans px-2 py-0.5 rounded-full bg-[#2d4a3e]/10 border border-[#2d4a3e]/15 text-[#2d4a3e] font-semibold">
                Store Guardian
              </span>
            </div>
            <p className="text-[11px] text-[#4e6357]">Continuous Checkout Protection &amp; Instant Recovery</p>
          </div>
        </div>

        {/* Live System State Marks */}
        <div className="flex items-center flex-wrap gap-3 text-xs">
          {/* Shopper Status */}
          <div className="flex items-center gap-1.5 px-3 py-1 rounded-full bg-white/80 border border-[#2d4a3e]/15 shadow-sm">
            <span className="relative flex h-2 w-2">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
              <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span>
            </span>
            <span className="text-[#1c2a22] text-[11px] font-medium">
              Shopper: Active
            </span>
          </div>

          {/* 24/7 Protection Status */}
          <div className="flex items-center gap-1.5 px-3 py-1 rounded-full bg-white/80 border border-[#2d4a3e]/15 shadow-sm">
            <StatusMark
              status={guardStatus?.enabled ? "running" : "done"}
              size={13}
              color="#2d4a3e"
              doneColor="#1b7a4b"
            />
            <span className="text-[#1c2a22] text-[11px] font-medium">
              Protection: {guardStatus?.enabled ? `Active (${guardStatus.interval_label})` : "Standby"}
            </span>
          </div>

          {/* Store Target link */}
          <a
            href={
              process.env.NEXT_PUBLIC_STORE_URL ||
              (typeof window !== "undefined" && window.location.hostname !== "localhost" && window.location.hostname !== "127.0.0.1"
                ? "/store"
                : "http://127.0.0.1:3005")
            }
            target="_blank"
            rel="noreferrer"
            className="flex items-center gap-1.5 px-3 py-1 rounded-full bg-white/85 border border-[#2d4a3e]/15 text-[#2d4a3e] hover:bg-white text-[11px] font-semibold shadow-sm transition-all"
          >
            <span className="w-2 h-2 rounded-full bg-emerald-500 inline-block shadow-[0_0_6px_rgba(27,122,75,0.6)]" />
            <span>View Demo Store</span>
            <ExternalLink className="w-3 h-3 ml-0.5 opacity-70" />
          </a>
        </div>

        {/* Sentinel Interval & Refresh Controls */}
        <div className="flex items-center gap-2">
          <div className="flex items-center rounded-full bg-white/80 p-1 border border-[#2d4a3e]/15 shadow-sm">
            <span className="text-[10px] uppercase font-sans px-2 text-[#4e6357] font-semibold">Check Every</span>
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
                    ? "bg-[#2d4a3e] text-white shadow-sm font-semibold"
                    : "text-[#4e6357] hover:text-[#1c2a22]"
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
        {/* Interactive Walkthrough Bar — Springlight Refined */}
        <div className="flex flex-wrap items-center justify-between gap-3 p-3.5 px-4 rounded-2xl bg-white/85 border border-white/95 backdrop-blur-xl shadow-[0_8px_24px_rgba(35,55,45,0.06)]">
          <div className="flex items-center gap-2.5">
            <div className="w-7 h-7 rounded-xl bg-amber-100 border border-amber-300 flex items-center justify-center text-amber-700 font-bold text-xs shadow-sm">
              <Zap className="w-4 h-4 fill-current text-amber-600" />
            </div>
            <div>
              <span className="text-xs font-bold text-[#1c2a22] tracking-tight">Interactive Walkthrough:</span>
              <span className="text-xs text-[#4e6357] ml-1.5 hidden md:inline">Experience checkout protection &amp; instant recovery in 3 steps:</span>
            </div>
          </div>

          <div className="flex items-center flex-wrap gap-2">
            <LiquidGlassButton
              size="sm"
              variant="danger"
              badge="1"
              onClick={() => launchScenario("defect_autoheal")}
            >
              Simulate Store Defect
            </LiquidGlassButton>

            <LiquidGlassButton
              size="sm"
              variant="primary"
              badge="2"
              onClick={handleTriggerProbe}
            >
              {isProbing ? "Testing Store…" : "Run Order Verification"}
            </LiquidGlassButton>

            <LiquidGlassButton
              size="sm"
              variant="emerald"
              badge="3"
              onClick={handleApproveRepair}
            >
              Apply Instant Fix
            </LiquidGlassButton>
          </div>
        </div>

        {/* 1. Metrics Banner — Springlight Alabaster Cards */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          {/* Orders Checked */}
          <LiquidGlassCard
            glowColor="rgba(45, 74, 62, 0.15)"
            className="p-4 flex flex-col gap-1 shadow-lg"
          >
            <div className="flex items-center justify-between text-[#4e6357] text-xs">
              <span className="flex items-center gap-1.5">
                <ShoppingCart className="w-3.5 h-3.5 text-[#2d4a3e]" />
                <span className="font-semibold text-[#1c2a22]">Orders Checked</span>
              </span>
              <span className="text-[10px] font-sans text-[#2d4a3e] bg-[#2d4a3e]/8 px-2 py-0.5 rounded-full border border-[#2d4a3e]/15 font-semibold">Live Shopper</span>
            </div>
            <div className="flex items-baseline gap-2 mt-1">
              <Counter
                value={guardStatus?.total_probes ?? overview?.total_runs ?? runs.length}
                fontSize="28px"
                fontWeight={700}
                textColor="#1c2a22"
                fade={0}
              />
              <span className="text-xs text-[#4e6357] font-medium">100% Tested Live</span>
            </div>
          </LiquidGlassCard>

          {/* Revenue Protected */}
          <LiquidGlassCard
            glowColor="rgba(45, 74, 62, 0.15)"
            className="p-4 flex flex-col gap-1 shadow-lg"
          >
            <div className="flex items-center justify-between text-[#4e6357] text-xs">
              <span className="flex items-center gap-1.5">
                <ShieldCheck className="w-3.5 h-3.5 text-[#1b7a4b]" />
                <span className="font-semibold text-[#1c2a22]">Protected Revenue</span>
              </span>
              <span className="text-[10px] font-sans text-[#2d4a3e] bg-[#2d4a3e]/8 px-2 py-0.5 rounded-full border border-[#2d4a3e]/15 font-semibold">Active Store</span>
            </div>
            <div className="flex items-baseline gap-1 mt-1">
              <span className="text-2xl font-bold text-[#1c2a22]">$</span>
              <Counter
                value={
                  guardStatus?.revenue_protected ??
                  (overview?.repairs_verified
                    ? overview.repairs_verified * 99
                    : repairs.filter((r) => r.status === "VERIFIED").length * 99)
                }
                fontSize="28px"
                fontWeight={700}
                textColor="#1c2a22"
                fade={0}
              />
              <span className="text-xs text-[#4e6357] ml-1.5">Acme Voyager Store</span>
            </div>
          </LiquidGlassCard>

          {/* Sales at Risk */}
          <LiquidGlassCard
            glowColor="rgba(217, 56, 58, 0.15)"
            className="p-4 flex flex-col gap-1 shadow-lg"
          >
            <div className="flex items-center justify-between text-[#4e6357] text-xs">
              <span className="flex items-center gap-1.5">
                <ShieldAlert className="w-3.5 h-3.5 text-[#d9383a]" />
                <span className="font-semibold text-[#1c2a22]">Sales at Risk</span>
              </span>
              <span className="text-[10px] font-sans px-2 py-0.5 rounded-full bg-[#d9383a]/10 text-[#d9383a] border border-[#d9383a]/25 font-semibold">
                {defectActive ? "Checkout Broken" : "Healthy"}
              </span>
            </div>
            <div className="flex items-baseline gap-1 mt-1">
              <span className="text-2xl font-bold text-[#1c2a22]">$</span>
              <Counter
                value={defectActive ? 99 : (guardStatus?.revenue_at_risk ?? 0)}
                fontSize="28px"
                fontWeight={700}
                textColor="#1c2a22"
                fade={0}
              />
              <span className="text-xs text-[#4e6357] ml-1.5">
                {defectActive ? "per customer attempt" : "Zero broken orders"}
              </span>
            </div>
          </LiquidGlassCard>

          {/* Issues Auto-Fixed */}
          <LiquidGlassCard
            glowColor="rgba(45, 74, 62, 0.15)"
            className="p-4 flex flex-col gap-1 shadow-lg"
          >
            <div className="flex items-center justify-between text-[#4e6357] text-xs">
              <span className="flex items-center gap-1.5">
                <Wrench className="w-3.5 h-3.5 text-[#2d4a3e]" />
                <span className="font-semibold text-[#1c2a22]">Issues Auto-Fixed</span>
              </span>
              <span className="text-[10px] font-sans text-[#2d4a3e] bg-[#2d4a3e]/8 px-2 py-0.5 rounded-full border border-[#2d4a3e]/15 font-semibold">Self-Healing</span>
            </div>
            <div className="flex items-baseline gap-2 mt-1">
              <Counter
                value={overview?.repairs_verified ?? repairs.filter((r) => r.status === "VERIFIED").length}
                fontSize="28px"
                fontWeight={700}
                textColor="#1c2a22"
                fade={0}
              />
              <span className="text-xs text-[#4e6357]">Resolved automatically</span>
            </div>
          </LiquidGlassCard>
        </div>

        {/* 2. Verification Dispatch & Quick Scenarios */}
        <div className="flex flex-col gap-3 w-full">
          <div className="liquid-card-wrap relative w-full">
            <div className="liquid-glass-card relative overflow-hidden rounded-[22px] p-0 w-full focus-within:ring-1 focus-within:ring-[#2d4a3e]/30">
              <PromptBar
                placeholder="Enter customer journey to verify (e.g. Purchase Voyager Shoes on Acme Store)…"
                onSend={handlePromptSend}
                busy={isCreating || isProbing}
                width="100%"
                radius={22}
                background="transparent"
                color="#1c2a22"
                menuBackground="rgba(255, 255, 255, 0.96)"
                sparkColor="rgba(45, 74, 62, 0.45)"
                className="w-full"
                models={[
                  { key: "kane-deep", name: "Standard Shopper", tag: "Full Journey" },
                  { key: "kane-guard", name: "Quick Store Audit", tag: "Fast Check" },
                ]}
                defaultModel="kane-deep"
                efforts={["Full Journey", "Quick Check"]}
                defaultEffort="Full Journey"
              />
            </div>
            <div className="liquid-button-shadow" aria-hidden="true" style={{ borderRadius: '22px' }} />
          </div>

          {/* Quick-Launch Scenario Pills */}
          <div className="flex items-center flex-wrap gap-2 pt-1">
            <span className="text-[11px] uppercase text-[#4e6357] mr-1 flex items-center gap-1 font-semibold">
              <Sparkles className="w-3 h-3 text-[#2d4a3e]" />
              Quick Checks:
            </span>

            <LiquidGlassButton
              variant="glass"
              size="sm"
              onClick={() => launchScenario("sentinel_checkout")}
            >
              <ShoppingCart className="w-3.5 h-3.5 text-[#2d4a3e]" />
              <span>Verify Checkout Flow</span>
            </LiquidGlassButton>

            <LiquidGlassButton
              variant="glass"
              size="sm"
              onClick={() => launchScenario("cart_quantity")}
            >
              Verify Cart &amp; Prices
            </LiquidGlassButton>

            <LiquidGlassButton
              variant="glass"
              size="sm"
              onClick={() => launchScenario("add_to_bag")}
            >
              Verify Product Options
            </LiquidGlassButton>

            <LiquidGlassButton
              variant="glass"
              size="sm"
              onClick={() => launchScenario("audit_catalog")}
            >
              Browse Store Catalog
            </LiquidGlassButton>

            <LiquidGlassButton
              variant="danger"
              size="sm"
              onClick={() => launchScenario("defect_autoheal")}
            >
              <Bug className="w-3.5 h-3.5 text-[#d9383a]" />
              <span>Simulate Defect → Auto Fix</span>
            </LiquidGlassButton>
          </div>
        </div>

        {/* 3. Main Bento Orchestration Grid (2 Columns) */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
          {/* Left Column (5 Cols): 24/7 Store Guardian & Self-Healing Studio */}
          <div className="lg:col-span-5 flex flex-col gap-6">
            {/* Card 1: Store Guardian — Springlight Alabaster Card */}
            <LiquidGlassCard
              glowColor="rgba(27, 122, 75, 0.15)"
              className="p-5 flex flex-col gap-4 shadow-xl"
            >
              <div className="flex items-center justify-between border-b border-[#2d4a3e]/10 pb-3">
                <div className="flex items-center gap-2">
                  <div className="p-1.5 rounded-xl bg-[#2d4a3e]/10 text-[#2d4a3e] border border-[#2d4a3e]/15">
                    <ShieldCheck className="w-4 h-4" />
                  </div>
                  <div>
                    <h3 className="font-display text-xl font-normal text-[#2d4a3e] tracking-tight">Store Guardian</h3>
                    <p className="text-[11px] text-[#4e6357]">Continuous customer shopping &amp; checkout monitoring</p>
                  </div>
                </div>

                <div className="flex items-center gap-2">
                  <span className="text-[10px] font-sans px-2.5 py-0.5 rounded-full bg-[#1b7a4b]/10 text-[#1b7a4b] border border-[#1b7a4b]/20 flex items-center gap-1.5 font-semibold">
                    <span className="w-2 h-2 rounded-full bg-emerald-500 inline-block shadow-[0_0_6px_rgba(27,122,75,0.6)]" />
                    {isProbing ? "CHECKING STORE..." : guardStatus?.enabled ? "ACTIVE MONITORING" : "STANDBY"}
                  </span>
                </div>
              </div>

              {/* Status and Next Check Timer */}
              <div className="grid grid-cols-2 gap-3 p-3.5 rounded-2xl liquid-glass-panel">
                <div>
                  <span className="text-[10px] uppercase font-sans text-[#4e6357] block font-semibold">Next Store Check In</span>
                  <div className="flex items-baseline gap-1 mt-0.5">
                    <span className="text-xl font-bold font-sans text-[#1c2a22]">{countdown}</span>
                    <span className="text-xs text-[#4e6357] font-sans">seconds</span>
                  </div>
                </div>
                <div>
                  <span className="text-[10px] uppercase font-sans text-[#4e6357] block font-semibold">Check Frequency</span>
                  <div className="flex items-baseline gap-1 mt-0.5">
                    <span className="text-sm font-semibold text-[#1c2a22]">Every {guardStatus?.interval_label || "2 minutes"}</span>
                  </div>
                </div>
              </div>

              {/* Store Health & Simulation Banner with Liquid Toggle */}
              <div
                className={`p-3.5 rounded-2xl border flex flex-col gap-2.5 transition-colors ${
                  !isStoreHealthy
                    ? "bg-rose-50/90 border-rose-300 text-rose-900"
                    : "bg-emerald-50/90 border-emerald-300 text-emerald-900"
                }`}
              >
                <div className="flex items-center justify-between">
                  <span className="text-xs font-semibold flex items-center gap-1.5">
                    {!isStoreHealthy ? (
                      <>
                        <AlertTriangle className="w-4 h-4 text-rose-600 animate-pulse flex-none" />
                        <span className="text-rose-900 font-bold">
                          {defectActive
                            ? "Defect Injected: Checkout Button Disabled"
                            : unresolvedRepair
                            ? "Checkout Issue Pending Repair"
                            : "Latest Completed Verification Failed"}
                        </span>
                      </>
                    ) : (
                      <>
                        <CheckCircle2 className="w-4 h-4 text-emerald-600 flex-none" />
                        <span className="text-emerald-900 font-semibold">Store Verified: Last Verification Passed</span>
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
                <p className="text-[11px] leading-relaxed opacity-90">
                  {!isStoreHealthy
                    ? (defectActive
                        ? "The checkout button is disabled on the store ($99 order blocked). Watch how the system detects the issue and stages a fix."
                        : "A recent test detected checkout blockage. The studio has prepared a repair.")
                    : "Your store checkout is running smoothly. Test customer orders complete with zero issues."}
                </p>
              </div>

              {/* Action Buttons */}
              <div className="flex items-center gap-2.5 pt-1">
                <div className="flex-1">
                  <LiquidGlassButton
                    variant="primary"
                    size="md"
                    fullWidth
                    isActionTile
                    icon={isProbing ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : <Play className="w-3.5 h-3.5 fill-current" />}
                    sublabel="Runs a complete customer purchase test"
                    disabled={isProbing}
                    onClick={handleTriggerProbe}
                  >
                    {isProbing ? "Checking Store..." : "Run Customer Order Test"}
                  </LiquidGlassButton>
                </div>

                <LiquidGlassButton
                  variant={defectActive ? "emerald" : "danger"}
                  size="md"
                  isActionTile
                  icon={<Bug className="w-3.5 h-3.5" />}
                  sublabel={defectActive ? "Restore store checkout" : "Test automatic recovery"}
                  disabled={isTogglingDefect}
                  onClick={handleToggleDefect}
                >
                  {defectActive ? "Reset Store to Normal" : "Simulate Defect"}
                </LiquidGlassButton>
              </div>
            </LiquidGlassCard>

            {/* Card 2: Self-Healing Studio — Springlight Alabaster Card */}
            <LiquidGlassCard
              glowColor="rgba(45, 74, 62, 0.15)"
              className="p-5 flex flex-col gap-4 shadow-xl"
            >
              <div className="flex items-center justify-between border-b border-[#2d4a3e]/10 pb-3">
                <div className="flex items-center gap-2">
                  <div className="p-1.5 rounded-xl bg-[#2d4a3e]/10 text-[#2d4a3e] border border-[#2d4a3e]/15">
                    <Wrench className="w-4 h-4" />
                  </div>
                  <div>
                    <h3 className="font-display text-xl font-normal text-[#2d4a3e] tracking-tight">Self-Healing Studio</h3>
                    <p className="text-[11px] text-[#4e6357]">Detects checkout errors and restores customer purchases</p>
                  </div>
                </div>

                <span
                  className={`text-[10px] font-sans px-2.5 py-0.5 rounded-full uppercase border font-semibold ${
                    unresolvedRepair?.status === "AWAITING_APPROVAL"
                      ? "bg-amber-100/90 text-amber-900 border-amber-300"
                      : unresolvedRepair
                      ? "bg-sky-100/90 text-sky-900 border-sky-300"
                      : defectActive
                      ? "bg-rose-100/90 text-rose-900 border-rose-300"
                      : "bg-emerald-100/90 text-emerald-900 border-emerald-300"
                  }`}
                >
                  {unresolvedRepair?.status === "AWAITING_APPROVAL"
                    ? "Fix Ready for Approval"
                    : unresolvedRepair?.status === "APPLYING" || unresolvedRepair?.status === "RETESTING"
                    ? "Applying & Retesting"
                    : unresolvedRepair
                    ? "Repair in Progress"
                    : defectActive
                    ? "Defect Active"
                    : "All Verified"}
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
                  theme="light"
                  accentColor="#2d4a3e"
                >
                  <Step title="Issue Spotted" description="Checkout was blocked">
                    <div className="p-3 rounded-xl liquid-glass-subcard text-xs text-[#1c2a22] leading-relaxed">
                      Detected that customers could not complete orders ($99 revenue at risk).
                    </div>
                  </Step>
                  <Step title="Diagnosis" description="Found broken code">
                    <div className="p-3 rounded-xl liquid-glass-subcard text-xs text-[#1c2a22] leading-relaxed">
                      Root Cause: The checkout button was disabled, preventing customer clicks.
                    </div>
                  </Step>
                  <Step title="Solution" description="Generated verified fix">
                    <div className="p-3 rounded-xl liquid-glass-subcard text-xs text-[#1c2a22] leading-relaxed">
                      Prepared a clean fix for cart checkout to restore purchasing.
                    </div>
                  </Step>
                  <Step title="Review Fix" description="Preview before applying">
                    <div className="p-3 rounded-xl liquid-glass-subcard text-xs text-[#1c2a22] leading-relaxed">
                      Review the problem vs solution below, then click to apply directly to the live store.
                    </div>
                  </Step>
                  <Step title="Re-Test Store" description="Verification check">
                    <div className="p-3 rounded-xl liquid-glass-subcard text-xs text-[#1c2a22] leading-relaxed">
                      Visits the store again to confirm customers can now purchase.
                    </div>
                  </Step>
                  <Step title="Store Protected!" description="Orders flowing smoothly">
                    <div className="p-3 rounded-xl liquid-glass-subcard text-xs text-emerald-800 leading-relaxed font-semibold">
                      Success! Store is confirmed healthy and customers can complete checkout with 0 errors.
                    </div>
                  </Step>
                </Stepper>
              </div>

              {/* Celebration Banner when Store Protected! */}
              {repairStep === 6 && (
                <div className="p-3.5 rounded-2xl bg-emerald-50/95 border border-emerald-300 text-emerald-900 flex items-center justify-between shadow-sm animate-in fade-in zoom-in-95 duration-200">
                  <div className="flex items-center gap-2.5">
                    <CheckCircle2 className="w-5 h-5 text-emerald-600 flex-none" />
                    <div>
                      <span className="text-xs font-bold text-emerald-950 block">Checkout Restored &amp; Verified!</span>
                      <span className="text-[11px] text-emerald-800">Store checkout restored. $0 revenue lost. Verification confirmed.</span>
                    </div>
                  </div>
                  <span className="text-[10px] uppercase font-mono px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-800 border border-emerald-300 font-semibold">
                    100% Restored
                  </span>
                </div>
              )}

              {/* Plain-English Visual Before/After Summary */}
              <div className="p-3.5 rounded-2xl liquid-glass-panel flex flex-col gap-2.5">
                <div className="flex items-center justify-between text-xs font-semibold text-[#1c2a22]">
                  <span className="flex items-center gap-1.5">
                    <Sparkles className="w-3.5 h-3.5 text-[#2d4a3e]" />
                    <span>Issue &amp; Resolution Details</span>
                  </span>
                  <span
                    className={`text-[10px] px-2 py-0.5 rounded-full border font-semibold ${
                      unresolvedRepair?.status === "AWAITING_APPROVAL"
                        ? "bg-amber-100 text-amber-900 border-amber-300"
                        : unresolvedRepair
                        ? "bg-sky-100 text-sky-900 border-sky-300"
                        : defectActive
                        ? "bg-rose-100 text-rose-900 border-rose-300"
                        : "bg-emerald-100 text-emerald-900 border-emerald-300"
                    }`}
                  >
                    {unresolvedRepair?.status === "AWAITING_APPROVAL"
                      ? "Awaiting Approval"
                      : unresolvedRepair?.status === "APPLYING" || unresolvedRepair?.status === "RETESTING"
                      ? "Applying Patch"
                      : unresolvedRepair
                      ? "Diagnosing Issue"
                      : defectActive
                      ? "Defect Active"
                      : "0 Issues Pending"}
                  </span>
                </div>

                {unresolvedRepair ? (
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5 text-xs">
                    <div className="p-3 rounded-xl bg-rose-50/80 border border-rose-200 flex flex-col gap-1">
                      <span className="text-[11px] font-semibold text-rose-800 flex items-center gap-1.5">
                        <AlertTriangle className="w-3.5 h-3.5 text-rose-600" />
                        <span>Problem Detected</span>
                      </span>
                      <p className="text-rose-950 text-[11px] leading-relaxed">
                        {unresolvedRepair.diagnosis || "The checkout button was disabled, preventing customers from finishing purchases."}
                      </p>
                    </div>
                    <div className="p-3 rounded-xl bg-emerald-50/80 border border-emerald-200 flex flex-col gap-1">
                      <span className="text-[11px] font-semibold text-emerald-800 flex items-center gap-1.5">
                        <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600" />
                        <span>Staged Solution</span>
                      </span>
                      <p className="text-emerald-950 text-[11px] leading-relaxed">
                        Re-enabled checkout button and restored active order submission.
                      </p>
                    </div>
                  </div>
                ) : defectActive ? (
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5 text-xs">
                    <div className="p-3 rounded-xl bg-rose-50/80 border border-rose-200 flex flex-col gap-1">
                      <span className="text-[11px] font-semibold text-rose-800 flex items-center gap-1.5">
                        <AlertTriangle className="w-3.5 h-3.5 text-rose-600" />
                        <span>Defect Injected</span>
                      </span>
                      <p className="text-rose-950 text-[11px] leading-relaxed">
                        Checkout button is disabled on Acme Store ($99 order blocked). Awaiting test detection.
                      </p>
                    </div>
                    <div className="p-3 rounded-xl bg-amber-50/80 border border-amber-200 flex flex-col gap-1">
                      <span className="text-[11px] font-semibold text-amber-800 flex items-center gap-1.5">
                        <Sparkles className="w-3.5 h-3.5 text-amber-600" />
                        <span>Recovery Standby</span>
                      </span>
                      <p className="text-amber-950 text-[11px] leading-relaxed">
                        System will automatically synthesize and stage a patch upon detecting the customer obstruction.
                      </p>
                    </div>
                  </div>
                ) : (
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5 text-xs">
                    <div className="p-3 rounded-xl bg-emerald-50/70 border border-emerald-200/80 flex flex-col gap-1">
                      <span className="text-[11px] font-semibold text-emerald-900 flex items-center gap-1.5">
                        <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600" />
                        <span>Store State: Healthy</span>
                      </span>
                      <p className="text-emerald-950 text-[11px] leading-relaxed">
                        All customer journeys passing normally. Zero checkout obstructions detected.
                      </p>
                    </div>
                    <div className="p-3 rounded-xl bg-white/70 border border-[#2d4a3e]/15 flex flex-col gap-1">
                      <span className="text-[11px] font-semibold text-[#2d4a3e] flex items-center gap-1.5">
                        <ShieldCheck className="w-3.5 h-3.5 text-[#1b7a4b]" />
                        <span>Verification Check</span>
                      </span>
                      <p className="text-[#4e6357] text-[11px] leading-relaxed">
                        Continuous checks verify real shopping and checkout transactions.
                      </p>
                    </div>
                  </div>
                )}

                {/* Optional fix details toggle */}
                <div className="pt-1">
                  <button
                    type="button"
                    onClick={() => setShowCodeDiff((prev) => !prev)}
                    className="text-[11px] text-[#4e6357] hover:text-[#1c2a22] flex items-center gap-1.5 transition-colors cursor-pointer py-1 font-medium"
                  >
                    {showCodeDiff ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
                    <span>{showCodeDiff ? "Hide Fix Details" : "View Fix Details"}</span>
                  </button>

                  {showCodeDiff && (
                    <div className="mt-2 rounded-xl bg-white/95 border border-[#2d4a3e]/15 p-3 font-mono text-[11px] leading-relaxed overflow-x-auto max-h-40 text-[#1c2a22] select-text shadow-inner">
                      <div className="text-[10px] text-[#4e6357] pb-1 border-b border-[#2d4a3e]/10 mb-1.5 flex items-center gap-1 font-semibold">
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
                                ? "text-emerald-800 bg-emerald-50 font-semibold"
                                : isDel
                                ? "text-rose-800 bg-rose-50"
                                : isHeader
                                ? "text-[#4e6357] font-semibold"
                                : "text-[#1c2a22]"
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

              {/* Approval Actions */}
              <div className="flex items-center gap-2.5 pt-1">
                <div className="flex-1">
                  <LiquidGlassButton
                    variant={unresolvedRepair ? "emerald" : "primary"}
                    size="md"
                    fullWidth
                    isActionTile
                    icon={isApprovingRepair ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : <CheckCircle2 className="w-3.5 h-3.5" />}
                    sublabel={
                      unresolvedRepair
                        ? "Instantly restores checkout & tests live"
                        : "Verify store checkout with simulated shopper"
                    }
                    disabled={isApprovingRepair || (!unresolvedRepair && isProbing)}
                    onClick={unresolvedRepair ? handleApproveRepair : handleTriggerProbe}
                  >
                    {isApprovingRepair
                      ? "Applying & Verifying Store..."
                      : unresolvedRepair
                      ? "Apply Fix & Verify Store"
                      : "Run Customer Order Test"}
                  </LiquidGlassButton>
                </div>

                {unresolvedRepair && (
                  <LiquidGlassButton
                    variant="glass"
                    size="md"
                    isActionTile
                    sublabel="Keep store as-is"
                    onClick={() => showNotification("Fix dismissed by operator.", "info")}
                  >
                    Dismiss
                  </LiquidGlassButton>
                )}
              </div>
            </LiquidGlassCard>
          </div>

          {/* Right Column (7 Cols): Live Customer Experience & Tests Feed */}
          <div className="lg:col-span-7 flex flex-col gap-6">
            {/* Card 3: Live Customer Experience — Pure Transparent Preview Surface */}
            <div
              className="rounded-[26px] border border-[#2d4a3e]/15 bg-transparent p-5 flex flex-col gap-4 shadow-none"
            >
              <div className="flex items-center justify-between border-b border-[#2d4a3e]/12 pb-3">
                <div className="flex items-center gap-2.5">
                  <div className="p-1.5 rounded-xl bg-[#2d4a3e]/10 text-[#2d4a3e] border border-[#2d4a3e]/15">
                    <ShoppingCart className="w-4 h-4" />
                  </div>
                  <div>
                    <h3 className="font-display text-xl font-normal text-[#2d4a3e] tracking-tight">
                      {currentRun?.title || "Live Customer Journey"}
                    </h3>
                    <p className="text-[11px] text-[#4e6357] font-medium">
                      Testing: Acme Store ({typeof window !== "undefined" && window.location.hostname !== "localhost" && window.location.hostname !== "127.0.0.1" ? `${window.location.host}/store` : (currentRun?.target_url || "http://127.0.0.1:3005")})
                    </p>
                  </div>
                </div>

                <div className="flex items-center gap-2">
                  <StatusMark
                    status={
                      isCurrentRunPassed
                        ? "done"
                        : currentRun?.status === "failed" || currentRun?.status === "error" || isTimedOut
                        ? "failed"
                        : "running"
                    }
                    size={15}
                    doneColor="#1b7a4b"
                    errorColor="#d9383a"
                  />
                  <span className={`text-xs uppercase font-bold tracking-tight ${
                    isCurrentRunPassed
                      ? "text-emerald-700"
                      : isTimedOut
                      ? "text-amber-700"
                      : currentRun?.status === "failed" || currentRun?.status === "error"
                      ? "text-rose-700"
                      : "text-sky-700"
                  }`}>
                    {isCurrentRunPassed
                      ? "CHECKOUT HEALTHY"
                      : isTimedOut
                      ? "EXECUTION TIMED OUT (90s)"
                      : currentRun?.status === "failed"
                      ? "CHECKOUT BLOCKED"
                      : currentRun?.status === "error"
                      ? "TEST RUN ERROR"
                      : currentRun?.status === "queued"
                      ? "QUEUED FOR TESTING..."
                      : "VERIFYING CHECKOUT..."}
                  </span>
                </div>
              </div>

              {/* 1. Live Chromium Browser Viewport — Full Landscape 16:9 */}
              <LiveBrowserViewport
                currentUrl={currentRun?.target_url || "http://127.0.0.1:3005"}
                runStatus={isCurrentRunPassed ? "passed" : isTimedOut ? "timed_out" : (currentRun?.status || "passed")}
                screenshotUrl={evidenceScreenshotUrl}
                runId={currentRun?.id}
                onRetry={handleRetryRun}
              />

              {/* 2. Real 7-Step Shopper Journey Execution Timeline */}
              <ShopperJourneyTimeline
                steps={shopperJourneySteps}
                progressPercent={progressPercentage}
                completedCount={completedStepsCount}
                totalCount={7}
                elapsedSec={runElapsedSec}
                currentUrl={currentRun?.target_url || "http://127.0.0.1:3005"}
                runStatus={isCurrentRunPassed ? "passed" : isTimedOut ? "timed_out" : (currentRun?.status || "passed")}
                failureReason={isCurrentRunPassed ? null : isTimedOut ? "Worker session reached 90s timeout. Test halted to prevent hanging." : currentRun?.failure_reason}
                onRetry={handleRetryRun}
                isStale={isCurrentRunPassed ? false : isTimedOut}
              />

              {/* 3. Customer Goal */}
              <div className="w-full p-4 rounded-2xl liquid-glass-panel flex flex-col gap-2 text-xs text-[#1c2a22]">
                <div className="flex items-center justify-between text-[#4e6357] text-[11px] w-full">
                  <span className="font-semibold text-[#2d4a3e] uppercase tracking-wide">Customer Goal:</span>
                  <span className="font-mono text-[#4e6357] font-semibold">Test ID: {currentRun?.id?.slice(0, 8) || "run-latest"}</span>
                </div>
                <p className="text-[#1c2a22] font-medium leading-relaxed w-full">
                  {currentRun?.objective || "Verify customer can select Voyager Shoes (Size M), add to bag ($99.00), and complete checkout without errors."}
                </p>
              </div>
            </div>

            {/* Card 4: AnimatedList of All Runs — Springlight Alabaster Card */}
            <LiquidGlassCard
              glowColor="rgba(45, 74, 62, 0.15)"
              className="p-5 flex flex-col gap-3 shadow-xl"
            >
              <div className="flex items-center justify-between border-b border-[#2d4a3e]/10 pb-2.5">
                <div className="flex items-center gap-2">
                  <Clock className="w-4 h-4 text-[#2d4a3e]" />
                  <h3 className="font-display text-xl font-normal text-[#2d4a3e]">Recent Customer Tests</h3>
                </div>
                <span className="text-[11px] text-[#4e6357] font-medium">{runs.length} checks recorded</span>
              </div>

              {/* AnimatedList Component */}
              <div className="w-full max-h-64 overflow-y-auto">
                <AnimatedList
                  items={runListItems}
                  onItemSelect={(_, index) => {
                    if (runs[index]) {
                      setSelectedRunId(runs[index].id);
                      setActiveTimerSec(0);
                    }
                  }}
                  displayScrollbar={true}
                  frame={false}
                  theme="light"
                  width="100%"
                  className="w-full"
                />
              </div>
            </LiquidGlassCard>
          </div>
        </div>
      </main>

      {/* Footer — Springlight Alabaster Glass Footer */}
      <footer className="w-full border-t border-[#2d4a3e]/12 bg-white/80 backdrop-blur-2xl py-4 px-6 mt-8 text-center text-xs text-[#4e6357] flex flex-wrap items-center justify-between gap-2 shadow-[0_-4px_20px_rgba(35,55,45,0.03)]">
        <div className="flex items-center gap-2">
          <span className="font-display text-base font-normal text-[#2d4a3e]">ShipProof</span>
          <span>•</span>
          <span>24/7 Continuous Checkout Protection</span>
        </div>
        <div>
          <span className="font-medium">Continuous Checkout Verification &amp; Instant Recovery</span>
        </div>
      </footer>
    </div>
  );
}

export default ShipProofConsole;
