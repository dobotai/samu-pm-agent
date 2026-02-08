#!/usr/bin/env python3
"""
Automation Scheduler - Cron-style job scheduling inside the FastAPI process.

Uses APScheduler's AsyncIOScheduler to trigger automations at configured times.
Reads automation definitions from config/automations.json.

Handles three CLI patterns for tool execution:
  - action_json:  script.py <action> '<json_params>'
  - argparse:     script.py <positional> --flag value
  - positional:   script.py <action> <arg1> <arg2> ...
"""

import asyncio
import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytz
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger


# Project root (parent of execution/)
PROJECT_ROOT = Path(__file__).parent.parent


class AutomationScheduler:
    """Manages scheduled automations with in-process cron-style triggers."""

    def __init__(self, config_path: str = None):
        if config_path is None:
            config_path = str(PROJECT_ROOT / "config" / "automations.json")
        self.config_path = config_path
        self.config: Dict[str, Any] = {}
        self.scheduler: Optional[AsyncIOScheduler] = None
        self.timezone = None

        # Runtime state per automation
        self.run_state: Dict[str, Dict[str, Any]] = {}

        # Log directory
        self.log_dir = PROJECT_ROOT / ".tmp" / "logs"
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.log_file = self.log_dir / "automations.jsonl"

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self):
        """Load config, register jobs, start the scheduler."""
        self.config = self._load_config()
        tz_name = self.config.get("timezone", "US/Eastern")
        self.timezone = pytz.timezone(tz_name)
        self.scheduler = AsyncIOScheduler(timezone=self.timezone)

        for auto in self.config.get("automations", []):
            self._init_state(auto)
            if auto.get("enabled", True):
                self._register_jobs(auto)

        self.scheduler.start()

        # Update next_run_time AFTER scheduler starts (slots aren't assigned until then)
        for auto in self.config.get("automations", []):
            if auto.get("enabled", True):
                self._update_next_run(auto["id"])

        print(f"[Scheduler] Started with timezone {tz_name}")
        for auto in self.config.get("automations", []):
            times = auto.get("schedule", {}).get("times", [])
            enabled = auto.get("enabled", True)
            next_t = self.run_state.get(auto["id"], {}).get("next_run_time", "?")
            print(f"[Scheduler]   {auto['name']} — {'ENABLED' if enabled else 'DISABLED'} — {', '.join(times)} — next: {next_t}")

    async def shutdown(self):
        """Gracefully shut down the scheduler."""
        if self.scheduler and self.scheduler.running:
            self.scheduler.shutdown(wait=False)
            print("[Scheduler] Shut down")

    # ------------------------------------------------------------------
    # Config
    # ------------------------------------------------------------------

    def _load_config(self) -> dict:
        with open(self.config_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def reload_config(self):
        """Hot-reload config and re-register all jobs."""
        self.config = self._load_config()
        # Remove all existing jobs
        if self.scheduler:
            self.scheduler.remove_all_jobs()
        for auto in self.config.get("automations", []):
            self._init_state(auto)
            if auto.get("enabled", True):
                self._register_jobs(auto)

    # ------------------------------------------------------------------
    # State
    # ------------------------------------------------------------------

    def _init_state(self, auto: dict):
        aid = auto["id"]
        if aid not in self.run_state:
            self.run_state[aid] = {
                "last_run_time": None,
                "last_run_status": None,
                "last_run_duration": None,
                "last_error": None,
                "next_run_time": None,
                "enabled": auto.get("enabled", True),
                "run_count": 0,
                "fail_count": 0,
                "currently_running": False,
            }

    # ------------------------------------------------------------------
    # Job registration
    # ------------------------------------------------------------------

    def _parse_days(self, days_str: str) -> str:
        """Convert schedule days to APScheduler day_of_week format."""
        if days_str == "*":
            return "*"
        return days_str  # "mon-fri", "mon,wed,fri" are already valid

    def _register_jobs(self, auto: dict):
        schedule = auto.get("schedule", {})
        days = self._parse_days(schedule.get("days", "mon-fri"))

        for time_str in schedule.get("times", []):
            hour, minute = map(int, time_str.split(":"))
            trigger = CronTrigger(
                hour=hour,
                minute=minute,
                day_of_week=days,
                timezone=self.timezone,
            )
            job_id = f"{auto['id']}_{time_str}"
            self.scheduler.add_job(
                self._run_automation_wrapper,
                trigger=trigger,
                args=[auto["id"], "scheduler"],
                id=job_id,
                name=f"{auto['name']} @ {time_str}",
                replace_existing=True,
            )

    def _update_next_run(self, automation_id: str):
        """Find the nearest next fire time across all jobs for this automation."""
        next_times = []
        for job in self.scheduler.get_jobs():
            if job.id.startswith(automation_id + "_"):
                nrt = getattr(job, 'next_run_time', None)
                if nrt:
                    next_times.append(nrt)
        if next_times:
            self.run_state[automation_id]["next_run_time"] = min(next_times).isoformat()

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    async def _run_automation_wrapper(self, automation_id: str, triggered_by: str = "scheduler"):
        """Wrapper that catches all exceptions so APScheduler doesn't lose the job."""
        try:
            await self.run_automation(automation_id, triggered_by)
        except Exception as e:
            print(f"[Scheduler] FATAL error in {automation_id}: {e}")

    async def run_automation(self, automation_id: str, triggered_by: str = "scheduler"):
        """Execute all steps of an automation sequentially."""
        auto = self._find_automation(automation_id)
        if not auto:
            print(f"[Scheduler] Automation not found: {automation_id}")
            return

        state = self.run_state[automation_id]

        # Concurrency guard
        if state["currently_running"]:
            print(f"[Scheduler] {automation_id} already running, skipping")
            return

        state["currently_running"] = True
        start_time = time.time()
        now = datetime.now(self.timezone)
        step_results = []
        context = {"step_outputs": {}, "timezone": self.timezone}
        error = None
        status = "success"

        # Determine time-of-day context for summary
        hour = now.hour
        if hour < 11:
            context["time_of_day"] = "morning"
        elif hour < 14:
            context["time_of_day"] = "midday"
        else:
            context["time_of_day"] = "afternoon"

        print(f"[Scheduler] Running {auto['name']} ({triggered_by}) — {context['time_of_day']}")

        try:
            for step in auto.get("steps", []):
                step_start = time.time()
                try:
                    result = await self.run_step(step, context)
                    context["step_outputs"][step["id"]] = result
                    step_results.append({
                        "id": step["id"],
                        "status": "success" if result.get("success", True) else "failed",
                        "duration": round(time.time() - step_start, 2),
                    })
                    print(f"[Scheduler]   Step {step['id']}: OK ({step_results[-1]['duration']}s)")
                except Exception as e:
                    step_results.append({
                        "id": step["id"],
                        "status": "failed",
                        "duration": round(time.time() - step_start, 2),
                        "error": str(e),
                    })
                    error = f"Step '{step['id']}' failed: {e}"
                    status = "failed"
                    print(f"[Scheduler]   Step {step['id']}: FAILED — {e}")
                    break  # Stop on first failure

        except Exception as e:
            error = str(e)
            status = "failed"
        finally:
            duration = round(time.time() - start_time, 2)
            state["currently_running"] = False
            state["last_run_time"] = now.isoformat()
            state["last_run_status"] = status
            state["last_run_duration"] = duration
            state["last_error"] = error
            state["run_count"] += 1
            if status == "failed":
                state["fail_count"] += 1

            # Update next run time
            if self.scheduler and self.scheduler.running:
                self._update_next_run(automation_id)

            # Log the run
            self._log_run(automation_id, triggered_by, status, duration, step_results, error, now)
            print(f"[Scheduler] {auto['name']} — {status.upper()} in {duration}s")

    async def run_step(self, step: dict, context: dict) -> dict:
        """Execute a single step via subprocess."""
        tool_path = PROJECT_ROOT / step["tool"]
        if not tool_path.exists():
            raise FileNotFoundError(f"Tool not found: {tool_path}")

        cli_pattern = step.get("cli_pattern", "action_json")
        cmd = [sys.executable, str(tool_path)]

        if cli_pattern == "action_json":
            # script.py <action> '<json_params>'
            if step.get("action"):
                cmd.append(step["action"])

            params = dict(step.get("params", {}))
            # Resolve input_steps reference
            if "input_steps" in params:
                input_data = {}
                for ref_id in params["input_steps"]:
                    if ref_id in context["step_outputs"]:
                        input_data[ref_id] = context["step_outputs"][ref_id].get("output", context["step_outputs"][ref_id])
                params["input_data"] = input_data
                del params["input_steps"]

            # Add time_of_day context if step uses it
            if step["tool"].endswith("summary_generator.py"):
                params["time_of_day"] = context.get("time_of_day", "update")

            # Resolve variables in all string params
            resolved = {}
            for k, v in params.items():
                resolved[k] = self._resolve(v, context) if isinstance(v, str) else v
            cmd.append(json.dumps(resolved))

        elif cli_pattern == "argparse":
            # script.py <positional> --flag value
            params = step.get("params", {})
            # Positional args first (keys without --)
            for k, v in params.items():
                if not k.startswith("--"):
                    cmd.append(self._resolve(str(v), context))
            # Then flags
            for k, v in params.items():
                if k.startswith("--"):
                    cmd.extend([k, self._resolve(str(v), context)])

        elif cli_pattern == "positional":
            # script.py <action> <arg1> <arg2> ...
            if step.get("action"):
                cmd.append(step["action"])
            for arg in step.get("params", {}).get("args", []):
                cmd.append(self._resolve(str(arg), context))

        # Run subprocess
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(PROJECT_ROOT),
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=180)

        stdout_text = stdout.decode("utf-8", errors="replace").strip()
        stderr_text = stderr.decode("utf-8", errors="replace").strip()

        if proc.returncode != 0:
            raise RuntimeError(f"Exit code {proc.returncode}: {stderr_text or stdout_text}")

        # Parse output
        try:
            output = json.loads(stdout_text)
        except json.JSONDecodeError:
            output = stdout_text

        return {"success": True, "output": output, "raw": stdout_text}

    # ------------------------------------------------------------------
    # Variable resolution
    # ------------------------------------------------------------------

    def _resolve(self, value: str, context: dict) -> str:
        """Resolve ${ENV_VAR} and ${steps.<id>.field} references."""
        if not isinstance(value, str) or "${" not in value:
            return value

        def replacer(match):
            ref = match.group(1)
            # Step output reference: steps.step_id.field
            if ref.startswith("steps."):
                parts = ref.split(".", 2)  # ["steps", "step_id", "field"]
                if len(parts) == 3:
                    step_id, field = parts[1], parts[2]
                    step_out = context.get("step_outputs", {}).get(step_id, {})
                    # Try output dict first, then raw
                    out = step_out.get("output", step_out)
                    if isinstance(out, dict):
                        val = out.get(field, "")
                    else:
                        val = str(out)
                    return str(val)
            # Environment variable
            return os.getenv(ref, "")

        return re.sub(r'\$\{([^}]+)\}', replacer, value)

    # ------------------------------------------------------------------
    # Management
    # ------------------------------------------------------------------

    def _find_automation(self, automation_id: str) -> Optional[dict]:
        for auto in self.config.get("automations", []):
            if auto["id"] == automation_id:
                return auto
        return None

    def enable_automation(self, automation_id: str):
        auto = self._find_automation(automation_id)
        if not auto:
            return
        self.run_state[automation_id]["enabled"] = True
        self._register_jobs(auto)

    def disable_automation(self, automation_id: str):
        if automation_id not in self.run_state:
            return
        self.run_state[automation_id]["enabled"] = False
        # Remove all jobs for this automation
        for job in list(self.scheduler.get_jobs()):
            if job.id.startswith(automation_id + "_"):
                job.remove()

    def trigger_now(self, automation_id: str):
        """Fire an automation immediately (returns a coroutine)."""
        return self.run_automation(automation_id, triggered_by="manual")

    # ------------------------------------------------------------------
    # Status / History
    # ------------------------------------------------------------------

    def get_status(self) -> dict:
        """Return status of all automations."""
        automations = []
        for auto in self.config.get("automations", []):
            aid = auto["id"]
            state = self.run_state.get(aid, {})
            automations.append({
                "id": aid,
                "name": auto.get("name", aid),
                "description": auto.get("description", ""),
                "enabled": state.get("enabled", True),
                "schedule": auto.get("schedule", {}),
                "last_run": {
                    "time": state.get("last_run_time"),
                    "status": state.get("last_run_status"),
                    "duration_seconds": state.get("last_run_duration"),
                    "error": state.get("last_error"),
                },
                "next_run": state.get("next_run_time"),
                "run_count": state.get("run_count", 0),
                "fail_count": state.get("fail_count", 0),
                "currently_running": state.get("currently_running", False),
            })
        return {
            "automations": automations,
            "scheduler_running": bool(self.scheduler and self.scheduler.running),
            "timezone": str(self.timezone),
        }

    def get_automation_status(self, automation_id: str) -> Optional[dict]:
        status = self.get_status()
        for a in status["automations"]:
            if a["id"] == automation_id:
                return a
        return None

    def get_run_history(self, automation_id: str, limit: int = 20) -> list:
        """Read run history from the JSONL log file."""
        if not self.log_file.exists():
            return []
        entries = []
        with open(self.log_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    if entry.get("automation_id") == automation_id:
                        entries.append(entry)
                except json.JSONDecodeError:
                    continue
        # Return most recent first
        return list(reversed(entries[-limit:]))

    # ------------------------------------------------------------------
    # Logging
    # ------------------------------------------------------------------

    def _log_run(self, automation_id, triggered_by, status, duration, steps, error, timestamp):
        entry = {
            "timestamp": timestamp.isoformat(),
            "automation_id": automation_id,
            "triggered_by": triggered_by,
            "status": status,
            "duration_seconds": duration,
            "steps": steps,
            "error": error,
        }
        with open(self.log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
