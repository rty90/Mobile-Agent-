from __future__ import annotations

import os
import socket
import subprocess
import time
from typing import Dict, Optional
from urllib.parse import urlparse


class ModelRuntime(object):
    DEFAULT_LOCAL_TEXT_MODEL = "Qwen/Qwen3.5-2B"
    DEFAULT_LOCAL_VL_MODEL = "Qwen/Qwen3-VL-2B-Instruct"
    DEFAULT_CLOUD_REVIEWER_MODEL = "qwen3.5-plus"
    DEFAULT_DASHSCOPE_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"

    def __init__(self) -> None:
        self.local_text_base_url = os.environ.get(
            "LOCAL_TEXT_REASONER_BASE_URL",
            "http://127.0.0.1:9000/v1",
        )
        self.local_vl_base_url = os.environ.get(
            "LOCAL_VL_REASONER_BASE_URL",
            "http://127.0.0.1:9001/v1",
        )
        self._owned_processes = {}

    def ensure_local_text_service(self) -> Dict[str, object]:
        return self._ensure_service(
            service_name="local_text",
            base_url=self.local_text_base_url,
            start_cmd=os.environ.get("LOCAL_TEXT_REASONER_START_CMD"),
        )

    def ensure_local_vl_service(self) -> Dict[str, object]:
        return self._ensure_service(
            service_name="local_vl",
            base_url=self.local_vl_base_url,
            start_cmd=os.environ.get("LOCAL_VL_REASONER_START_CMD"),
        )

    def local_vl_enabled(self) -> bool:
        value = str(os.environ.get("REASONING_ENABLE_LOCAL_VL", "0")).strip().lower()
        return value in {"1", "true", "yes", "on"}

    def shutdown_owned_processes(self) -> None:
        for service_name, process in list(self._owned_processes.items()):
            if process.poll() is not None:
                continue
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
            finally:
                self._owned_processes.pop(service_name, None)

    def cloud_reviewer_configured(self) -> bool:
        return bool(self.cloud_reviewer_base_url() and self.cloud_reviewer_api_key() and self.cloud_reviewer_model())

    def cloud_reviewer_base_url(self) -> str:
        return (
            os.environ.get("CLOUD_REVIEWER_BASE_URL")
            or os.environ.get("QWEN_BASE_URL")
            or os.environ.get("DASHSCOPE_BASE_URL")
            or (self.DEFAULT_DASHSCOPE_BASE_URL if self.cloud_reviewer_api_key() else "")
        )

    def cloud_reviewer_api_key(self) -> str:
        return (
            os.environ.get("CLOUD_REVIEWER_API_KEY")
            or os.environ.get("QWEN_API_KEY")
            or os.environ.get("DASHSCOPE_API_KEY")
            or ""
        )

    def cloud_reviewer_model(self) -> str:
        return (
            os.environ.get("CLOUD_REVIEWER_MODEL")
            or os.environ.get("QWEN_MODEL")
            or os.environ.get("DASHSCOPE_MODEL")
            or (self.DEFAULT_CLOUD_REVIEWER_MODEL if self.cloud_reviewer_api_key() else "")
        )

    def _ensure_service(
        self,
        service_name: str,
        base_url: str,
        start_cmd: Optional[str],
    ) -> Dict[str, object]:
        if self._is_service_available(base_url):
            return {
                "available": True,
                "started": False,
                "base_url": base_url,
                "service_name": service_name,
            }

        if not start_cmd:
            return {
                "available": False,
                "started": False,
                "base_url": base_url,
                "service_name": service_name,
                "reason": "No start command was configured.",
            }

        process = subprocess.Popen(
            start_cmd,
            shell=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        self._owned_processes[service_name] = process

        deadline = time.time() + 25
        while time.time() < deadline:
            if self._is_service_available(base_url):
                return {
                    "available": True,
                    "started": True,
                    "base_url": base_url,
                    "service_name": service_name,
                }
            if process.poll() is not None:
                break
            time.sleep(0.5)

        self.shutdown_owned_processes()
        return {
            "available": False,
            "started": True,
            "base_url": base_url,
            "service_name": service_name,
            "reason": "The local model service did not become ready in time.",
        }

    @staticmethod
    def _is_service_available(base_url: str) -> bool:
        parsed = urlparse(base_url)
        host = parsed.hostname or "127.0.0.1"
        port = parsed.port
        if not port:
            port = 443 if parsed.scheme == "https" else 80
        try:
            with socket.create_connection((host, port), timeout=1.0):
                return True
        except OSError:
            return False
