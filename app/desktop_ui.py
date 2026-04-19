from __future__ import annotations

from datetime import datetime
import json
import os
import queue
import subprocess
import threading
import traceback
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Any, Dict, Optional

from app.main import LOG_PATH, SCREENSHOT_ROOT, run_task
from app.task_types import (
    TASK_CREATE_REMINDER,
    TASK_EXTRACT_AND_COPY,
    TASK_GUIDED_UI_TASK,
    TASK_READ_CURRENT_SCREEN,
    TASK_SEND_MESSAGE,
    TASK_UNSUPPORTED,
)
from app.utils.adb import ADBClient, ADBError, find_adb_path


TASK_TYPE_OPTIONS = [
    "",
    TASK_SEND_MESSAGE,
    TASK_EXTRACT_AND_COPY,
    TASK_CREATE_REMINDER,
    TASK_READ_CURRENT_SCREEN,
    TASK_GUIDED_UI_TASK,
    TASK_UNSUPPORTED,
]
PLANNER_BACKEND_OPTIONS = ["rule", "openai"]
REASONER_BACKEND_OPTIONS = ["rule", "local", "openai", "stack"]
AGENT_MODE_OPTIONS = ["", "bounded", "interactive"]
DESKTOP_UI_HISTORY_PATH = "data/logs/desktop_ui_history.json"
DESKTOP_UI_HISTORY_LIMIT = 12


def build_run_kwargs(
    task_text: str,
    device_id: str = "",
    task_type: str = "",
    planner_backend: str = "rule",
    reasoner_backend: str = "stack",
    agent_mode: str = "",
    max_steps: Any = 3,
    dry_run: bool = False,
    auto_confirm: bool = True,
) -> Dict[str, Any]:
    task = str(task_text or "").strip()
    if not task:
        raise ValueError("Task text cannot be empty.")

    return {
        "task_text": task,
        "device_id": str(device_id or "").strip() or None,
        "planner_backend": planner_backend,
        "task_type_override": str(task_type or "").strip() or None,
        "agent_mode": str(agent_mode or "").strip() or None,
        "reasoner_backend": reasoner_backend,
        "max_steps": max(1, int(max_steps)),
        "dry_run": bool(dry_run),
        "auto_confirm": bool(auto_confirm),
    }


def get_device_status_report(device_id: str = "") -> Dict[str, Any]:
    requested_device = str(device_id or "").strip() or None
    try:
        adb_path = find_adb_path()
    except Exception as exc:
        return {
            "ok": False,
            "adb_path": "",
            "requested_device": requested_device,
            "connected": False,
            "devices": [],
            "message": str(exc),
        }

    try:
        adb = ADBClient(adb_path=adb_path, device_id=requested_device)
        adb.start_server()
        devices = adb.list_devices(only_ready=False)
        ready_devices = [item for item in devices if item.get("status") == "device"]
        if requested_device:
            connected = any(item.get("device_id") == requested_device and item.get("status") == "device" for item in devices)
        else:
            connected = bool(ready_devices)
        if connected:
            message = "ADB is ready."
        elif devices:
            message = "ADB is reachable, but no ready device matches the current selection."
        else:
            message = "ADB is reachable, but no emulator or phone is connected."
        return {
            "ok": True,
            "adb_path": adb_path,
            "requested_device": requested_device,
            "connected": connected,
            "devices": devices,
            "message": message,
        }
    except Exception as exc:
        return {
            "ok": False,
            "adb_path": adb_path,
            "requested_device": requested_device,
            "connected": False,
            "devices": [],
            "message": str(exc),
        }


def open_path_in_shell(path: str) -> bool:
    target = os.path.abspath(path)
    if not os.path.exists(target):
        return False
    try:
        if hasattr(os, "startfile"):
            os.startfile(target)
            return True
        subprocess.Popen(["xdg-open", target])
        return True
    except Exception:
        return False
    return False


def get_environment_status_report() -> Dict[str, Any]:
    api_key = os.environ.get("DASHSCOPE_API_KEY") or os.environ.get("QWEN_API_KEY")
    local_text_url = os.environ.get("LOCAL_TEXT_REASONER_BASE_URL", "").strip()
    local_text_model = os.environ.get("LOCAL_TEXT_REASONER_MODEL", "").strip()
    timeout_seconds = os.environ.get("REASONING_REQUEST_TIMEOUT_SECONDS", "").strip() or "<default>"
    local_vl_enabled = os.environ.get("REASONING_ENABLE_LOCAL_VL", "1").strip() != "0"
    disable_local_after_failure = (
        os.environ.get("REASONING_DISABLE_LOCAL_TEXT_AFTER_FAILURE", "0").strip() == "1"
    )
    cloud_base_url = (
        os.environ.get("DASHSCOPE_BASE_URL")
        or os.environ.get("QWEN_BASE_URL")
        or "https://dashscope.aliyuncs.com/compatible-mode/v1"
    )
    return {
        "cloud_api_configured": bool(api_key),
        "cloud_base_url": cloud_base_url,
        "local_text_configured": bool(local_text_url),
        "local_text_url": local_text_url or "<not set>",
        "local_text_model": local_text_model or "<not set>",
        "local_vl_enabled": local_vl_enabled,
        "disable_local_text_after_failure": disable_local_after_failure,
        "timeout_seconds": timeout_seconds,
    }


def load_recent_tasks(
    history_path: str = DESKTOP_UI_HISTORY_PATH,
    limit: int = DESKTOP_UI_HISTORY_LIMIT,
) -> list[Dict[str, Any]]:
    target = os.path.abspath(history_path)
    if not os.path.exists(target):
        return []
    try:
        with open(target, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except Exception:
        return []
    if not isinstance(payload, list):
        return []
    items = [item for item in payload if isinstance(item, dict)]
    return items[: max(1, int(limit))]


def save_recent_task(
    task_text: str,
    device_id: str = "",
    task_type: str = "",
    reasoner_backend: str = "",
    agent_mode: str = "",
    history_path: str = DESKTOP_UI_HISTORY_PATH,
    limit: int = DESKTOP_UI_HISTORY_LIMIT,
) -> list[Dict[str, Any]]:
    entry = {
        "task_text": str(task_text or "").strip(),
        "device_id": str(device_id or "").strip(),
        "task_type": str(task_type or "").strip(),
        "reasoner_backend": str(reasoner_backend or "").strip(),
        "agent_mode": str(agent_mode or "").strip(),
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    if not entry["task_text"]:
        return load_recent_tasks(history_path=history_path, limit=limit)

    existing = load_recent_tasks(history_path=history_path, limit=max(1, int(limit)) * 3)
    deduped = [
        item
        for item in existing
        if str(item.get("task_text") or "").strip().lower() != entry["task_text"].lower()
    ]
    payload = [entry] + deduped
    payload = payload[: max(1, int(limit))]

    target = os.path.abspath(history_path)
    os.makedirs(os.path.dirname(target), exist_ok=True)
    with open(target, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
    return payload


def format_history_label(entry: Dict[str, Any]) -> str:
    task_text = str(entry.get("task_text") or "").strip() or "<empty task>"
    timestamp = str(entry.get("updated_at") or "").strip()
    reasoner_backend = str(entry.get("reasoner_backend") or "").strip()
    parts = [task_text]
    meta = []
    if reasoner_backend:
        meta.append(reasoner_backend)
    if timestamp:
        meta.append(timestamp)
    if meta:
        parts.append(" | ".join(meta))
    return " | ".join(parts)


class DesktopAgentUI(object):
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Mobile Agent Desktop Console")
        self.root.geometry("1080x760")
        self.root.minsize(980, 700)
        self._events: "queue.Queue[Dict[str, Any]]" = queue.Queue()
        self._worker: Optional[threading.Thread] = None

        self.task_var = tk.StringVar()
        self.device_var = tk.StringVar()
        self.task_type_var = tk.StringVar(value="")
        self.planner_backend_var = tk.StringVar(value="rule")
        self.reasoner_backend_var = tk.StringVar(value="stack")
        self.agent_mode_var = tk.StringVar(value="")
        self.max_steps_var = tk.StringVar(value="5")
        self.dry_run_var = tk.BooleanVar(value=False)
        self.auto_confirm_var = tk.BooleanVar(value=True)
        self.status_var = tk.StringVar(value="Ready")
        self.device_status_var = tk.StringVar(value="Device status: unknown")
        self.env_status_var = tk.StringVar(value="Env status: unknown")
        self.history_var = tk.StringVar(value="")
        self._history_entries: list[Dict[str, Any]] = []

        self._build_layout()
        self._refresh_environment_status()
        self._refresh_history_options()
        self.root.after(120, self._poll_events)

    def _build_layout(self) -> None:
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(2, weight=1)

        header = ttk.Frame(self.root, padding=12)
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)

        title = ttk.Label(
            header,
            text="Mobile Agent Desktop Console",
            font=("Segoe UI", 15, "bold"),
        )
        title.grid(row=0, column=0, sticky="w")

        subtitle = ttk.Label(
            header,
            text="Input a natural-language task, choose execution options, and run the Android GUI agent from the desktop.",
        )
        subtitle.grid(row=1, column=0, sticky="w", pady=(4, 0))

        device_status = ttk.Label(header, textvariable=self.device_status_var)
        device_status.grid(row=2, column=0, sticky="w", pady=(8, 0))

        env_status = ttk.Label(header, textvariable=self.env_status_var)
        env_status.grid(row=3, column=0, sticky="w", pady=(4, 0))

        form = ttk.LabelFrame(self.root, text="Run Configuration", padding=12)
        form.grid(row=1, column=0, sticky="nsew", padx=12)
        for col in range(4):
            form.columnconfigure(col, weight=1)

        ttk.Label(form, text="Recent Tasks").grid(row=0, column=0, sticky="w")
        self.history_combo = ttk.Combobox(form, textvariable=self.history_var, state="readonly")
        self.history_combo.grid(row=1, column=0, columnspan=3, sticky="ew", pady=(4, 10))
        ttk.Button(form, text="Load Recent", command=self._load_selected_history).grid(
            row=1, column=3, sticky="ew", pady=(4, 10)
        )

        ttk.Label(form, text="Task").grid(row=2, column=0, sticky="w")
        self.task_entry = tk.Text(form, height=5, wrap="word")
        self.task_entry.grid(row=3, column=0, columnspan=4, sticky="nsew", pady=(4, 10))
        self.task_entry.insert("1.0", "open keep and create a note, then type 'hello from desktop ui'")

        ttk.Label(form, text="Device ID").grid(row=4, column=0, sticky="w")
        ttk.Entry(form, textvariable=self.device_var).grid(row=5, column=0, sticky="ew", padx=(0, 8))

        ttk.Label(form, text="Task Type").grid(row=4, column=1, sticky="w")
        ttk.Combobox(
            form,
            textvariable=self.task_type_var,
            values=TASK_TYPE_OPTIONS,
            state="readonly",
        ).grid(row=5, column=1, sticky="ew", padx=(0, 8))

        ttk.Label(form, text="Planner Backend").grid(row=4, column=2, sticky="w")
        ttk.Combobox(
            form,
            textvariable=self.planner_backend_var,
            values=PLANNER_BACKEND_OPTIONS,
            state="readonly",
        ).grid(row=5, column=2, sticky="ew", padx=(0, 8))

        ttk.Label(form, text="Reasoner Backend").grid(row=4, column=3, sticky="w")
        ttk.Combobox(
            form,
            textvariable=self.reasoner_backend_var,
            values=REASONER_BACKEND_OPTIONS,
            state="readonly",
        ).grid(row=5, column=3, sticky="ew")

        ttk.Label(form, text="Agent Mode").grid(row=6, column=0, sticky="w", pady=(10, 0))
        ttk.Combobox(
            form,
            textvariable=self.agent_mode_var,
            values=AGENT_MODE_OPTIONS,
            state="readonly",
        ).grid(row=7, column=0, sticky="ew", padx=(0, 8))

        ttk.Label(form, text="Max Steps").grid(row=6, column=1, sticky="w", pady=(10, 0))
        ttk.Spinbox(form, from_=1, to=20, textvariable=self.max_steps_var).grid(
            row=7, column=1, sticky="ew", padx=(0, 8)
        )

        ttk.Checkbutton(form, text="Dry Run", variable=self.dry_run_var).grid(
            row=7, column=2, sticky="w"
        )
        ttk.Checkbutton(form, text="Auto Confirm", variable=self.auto_confirm_var).grid(
            row=7, column=3, sticky="w"
        )

        actions = ttk.Frame(form)
        actions.grid(row=8, column=0, columnspan=4, sticky="ew", pady=(14, 0))
        actions.columnconfigure(5, weight=1)

        self.run_button = ttk.Button(actions, text="Run Task", command=self._start_run)
        self.run_button.grid(row=0, column=0, sticky="w")

        ttk.Button(actions, text="Dry Run", command=self._start_dry_run).grid(
            row=0, column=1, sticky="w", padx=(8, 0)
        )
        ttk.Button(actions, text="Check Device", command=self._start_device_check).grid(
            row=0, column=2, sticky="w", padx=(8, 0)
        )
        ttk.Button(actions, text="Check Env", command=self._show_environment_status).grid(
            row=0, column=3, sticky="w", padx=(8, 0)
        )
        ttk.Button(actions, text="Open Logs", command=self._open_logs).grid(
            row=0, column=4, sticky="w", padx=(8, 0)
        )
        ttk.Button(actions, text="Open Screenshots", command=self._open_screenshots).grid(
            row=0, column=5, sticky="w", padx=(8, 0)
        )
        ttk.Button(actions, text="Clear Output", command=self._clear_output).grid(
            row=0, column=6, sticky="w", padx=(8, 0)
        )

        ttk.Label(actions, textvariable=self.status_var).grid(row=0, column=7, sticky="e")

        output_frame = ttk.LabelFrame(self.root, text="Execution Output", padding=12)
        output_frame.grid(row=2, column=0, sticky="nsew", padx=12, pady=(12, 12))
        output_frame.columnconfigure(0, weight=1)
        output_frame.rowconfigure(0, weight=1)

        self.output_text = tk.Text(output_frame, wrap="word")
        self.output_text.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(output_frame, orient="vertical", command=self.output_text.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.output_text.configure(yscrollcommand=scrollbar.set)

    def _clear_output(self) -> None:
        self.output_text.delete("1.0", tk.END)
        self.status_var.set("Ready")

    def _set_running(self, running: bool) -> None:
        if running:
            self.run_button.configure(state="disabled")
            self.status_var.set("Running...")
        else:
            self.run_button.configure(state="normal")

    def _refresh_environment_status(self) -> None:
        report = get_environment_status_report()
        status_bits = [
            "cloud={0}".format("yes" if report.get("cloud_api_configured") else "no"),
            "local_text={0}".format("yes" if report.get("local_text_configured") else "no"),
            "local_vl={0}".format("on" if report.get("local_vl_enabled") else "off"),
            "timeout={0}s".format(report.get("timeout_seconds")),
        ]
        self.env_status_var.set("Env status: " + " | ".join(status_bits))

    def _refresh_history_options(self) -> None:
        self._history_entries = load_recent_tasks()
        labels = [format_history_label(item) for item in self._history_entries]
        self.history_combo.configure(values=labels)
        if labels:
            self.history_var.set(labels[0])
        else:
            self.history_var.set("")

    def _load_selected_history(self) -> None:
        selected_label = self.history_var.get().strip()
        if not selected_label:
            messagebox.showinfo("Recent Tasks", "No recent task is available yet.")
            return
        for item in self._history_entries:
            if format_history_label(item) != selected_label:
                continue
            self.task_entry.delete("1.0", tk.END)
            self.task_entry.insert("1.0", item.get("task_text") or "")
            self.device_var.set(item.get("device_id") or "")
            self.task_type_var.set(item.get("task_type") or "")
            self.reasoner_backend_var.set(item.get("reasoner_backend") or "stack")
            self.agent_mode_var.set(item.get("agent_mode") or "")
            self.status_var.set("Loaded recent task")
            return
        messagebox.showinfo("Recent Tasks", "The selected history entry is no longer available.")

    def _start_run(self) -> None:
        self._queue_task_run(force_dry_run=None)

    def _start_dry_run(self) -> None:
        self._queue_task_run(force_dry_run=True)

    def _queue_task_run(self, force_dry_run: Optional[bool]) -> None:
        if self._worker and self._worker.is_alive():
            messagebox.showinfo("Task Running", "A task is already running. Please wait for it to finish.")
            return

        try:
            kwargs = build_run_kwargs(
                task_text=self.task_entry.get("1.0", tk.END),
                device_id=self.device_var.get(),
                task_type=self.task_type_var.get(),
                planner_backend=self.planner_backend_var.get(),
                reasoner_backend=self.reasoner_backend_var.get(),
                agent_mode=self.agent_mode_var.get(),
                max_steps=self.max_steps_var.get(),
                dry_run=self.dry_run_var.get() if force_dry_run is None else force_dry_run,
                auto_confirm=self.auto_confirm_var.get(),
            )
        except Exception as exc:
            messagebox.showerror("Invalid Input", str(exc))
            return

        self._set_running(True)
        self.output_text.delete("1.0", tk.END)
        self.output_text.insert("1.0", "Running task...\n")
        save_recent_task(
            task_text=kwargs["task_text"],
            device_id=kwargs.get("device_id") or "",
            task_type=kwargs.get("task_type_override") or "",
            reasoner_backend=kwargs.get("reasoner_backend") or "",
            agent_mode=kwargs.get("agent_mode") or "",
        )
        self._refresh_history_options()

        self._worker = threading.Thread(target=self._run_task_worker, args=(kwargs,), daemon=True)
        self._worker.start()

    def _start_device_check(self) -> None:
        if self._worker and self._worker.is_alive():
            messagebox.showinfo("Task Running", "Please wait until the current task finishes before checking device status.")
            return
        self._set_running(True)
        self.output_text.delete("1.0", tk.END)
        self.output_text.insert("1.0", "Checking adb and connected devices...\n")
        self._worker = threading.Thread(target=self._device_check_worker, daemon=True)
        self._worker.start()

    def _device_check_worker(self) -> None:
        report = get_device_status_report(self.device_var.get())
        self._events.put({"type": "device_status", "payload": report})

    def _run_task_worker(self, kwargs: Dict[str, Any]) -> None:
        try:
            result = run_task(**kwargs)
            self._events.put({"type": "result", "payload": result})
        except Exception:
            self._events.put({"type": "error", "payload": traceback.format_exc()})

    def _poll_events(self) -> None:
        try:
            while True:
                event = self._events.get_nowait()
                event_type = event.get("type")
                if event_type == "result":
                    self._handle_result(event.get("payload") or {})
                elif event_type == "device_status":
                    self._handle_device_status(event.get("payload") or {})
                elif event_type == "error":
                    self._handle_error(str(event.get("payload") or "Unknown error"))
        except queue.Empty:
            pass
        finally:
            self.root.after(120, self._poll_events)

    def _handle_result(self, result: Dict[str, Any]) -> None:
        self._set_running(False)
        success = bool(result.get("success"))
        self.status_var.set("Completed successfully" if success else "Completed with failure")
        self.output_text.delete("1.0", tk.END)
        self.output_text.insert("1.0", json.dumps(result, ensure_ascii=False, indent=2))
        self._refresh_device_status_from_result(result)

    def _handle_error(self, error_text: str) -> None:
        self._set_running(False)
        self.status_var.set("Execution error")
        self.output_text.delete("1.0", tk.END)
        self.output_text.insert("1.0", error_text)
        messagebox.showerror("Execution Error", "The task failed before returning a normal result. See the output panel.")

    def _handle_device_status(self, report: Dict[str, Any]) -> None:
        self._set_running(False)
        ok = bool(report.get("ok"))
        connected = bool(report.get("connected"))
        devices = report.get("devices") or []
        if connected:
            self.status_var.set("Device ready")
        elif ok:
            self.status_var.set("ADB ready, device missing")
        else:
            self.status_var.set("ADB check failed")

        device_lines = [
            "ADB path: {0}".format(report.get("adb_path") or "<not found>"),
            "Requested device: {0}".format(report.get("requested_device") or "<auto>"),
            "Message: {0}".format(report.get("message") or ""),
            "",
            "Devices:",
        ]
        if devices:
            for item in devices:
                device_lines.append("- {0} [{1}]".format(item.get("device_id"), item.get("status")))
        else:
            device_lines.append("- none")
        self.output_text.delete("1.0", tk.END)
        self.output_text.insert("1.0", "\n".join(device_lines))
        self.device_status_var.set(
            "Device status: {0}".format("ready" if connected else "not ready")
        )

    def _refresh_device_status_from_result(self, result: Dict[str, Any]) -> None:
        logs_path = result.get("logs_path") or LOG_PATH
        if result.get("success"):
            self.device_status_var.set("Device status: task completed")
        else:
            self.device_status_var.set("Device status: task ended with failure")
        if logs_path and os.path.exists(logs_path):
            self.status_var.set("{0} | logs updated".format(self.status_var.get()))

    def _open_logs(self) -> None:
        log_dir = os.path.dirname(os.path.abspath(LOG_PATH))
        if not open_path_in_shell(log_dir):
            messagebox.showerror("Open Logs Failed", "Unable to open the log directory.")

    def _open_screenshots(self) -> None:
        if not open_path_in_shell(SCREENSHOT_ROOT):
            messagebox.showerror("Open Screenshots Failed", "Unable to open the screenshots directory.")

    def _show_environment_status(self) -> None:
        report = get_environment_status_report()
        self._refresh_environment_status()
        env_lines = [
            "Cloud API configured: {0}".format("yes" if report.get("cloud_api_configured") else "no"),
            "Cloud base URL: {0}".format(report.get("cloud_base_url")),
            "Local text configured: {0}".format("yes" if report.get("local_text_configured") else "no"),
            "Local text URL: {0}".format(report.get("local_text_url")),
            "Local text model: {0}".format(report.get("local_text_model")),
            "Local VL enabled: {0}".format("yes" if report.get("local_vl_enabled") else "no"),
            "Disable local text after failure: {0}".format(
                "yes" if report.get("disable_local_text_after_failure") else "no"
            ),
            "Reasoning timeout: {0}".format(report.get("timeout_seconds")),
        ]
        self.output_text.delete("1.0", tk.END)
        self.output_text.insert("1.0", "\n".join(env_lines))
        self.status_var.set("Environment inspected")


def main() -> int:
    root = tk.Tk()
    style = ttk.Style(root)
    if "vista" in style.theme_names():
        style.theme_use("vista")
    DesktopAgentUI(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
