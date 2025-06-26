import os
import zipfile
import requests
import logging
import time
from typing import Optional, Callable, Dict, Any

class UpgradeDownloader:
    """
    Vivian-grade, observable, secure upgrade downloader and extractor.

    Features:
      - Audit log for all downloads and extractions
      - Alert/metrics hooks for completion/failure (Slack/email/webhook/Prometheus-ready)
      - Pre/post hooks for validation, backup, or notification
      - Supports signature/hash verification
      - Handles download retries, network errors, and progress
      - Explainability/reporting hooks
      - REST API ready (can be integrated)
    """

    def __init__(
        self,
        url: str,
        save_path: str,
        audit_log_path: str = "upgrade_downloader_audit.jsonl",
        pre_download_hook: Optional[Callable[[str], None]] = None,
        post_download_hook: Optional[Callable[[str, bool], None]] = None,
        pre_extract_hook: Optional[Callable[[str], None]] = None,
        post_extract_hook: Optional[Callable[[str, bool], None]] = None,
        alert_cb: Optional[Callable[[str, Dict[str, Any]], None]] = None,
        metrics_cb: Optional[Callable[[str, float], None]] = None,
        signature_check_cb: Optional[Callable[[str], bool]] = None,
        explainability_cb: Optional[Callable[[Dict[str, Any]], None]] = None,
        max_retries: int = 2,
        retry_delay: int = 2
    ):
        self.url = url
        self.save_path = save_path
        self.audit_log_path = audit_log_path
        self.pre_download_hook = pre_download_hook
        self.post_download_hook = post_download_hook
        self.pre_extract_hook = pre_extract_hook
        self.post_extract_hook = post_extract_hook
        self.alert_cb = alert_cb
        self.metrics_cb = metrics_cb
        self.signature_check_cb = signature_check_cb
        self.explainability_cb = explainability_cb
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self._log = logging.getLogger("UpgradeDownloader")

    def _audit(self, action: str, data: dict):
        entry = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "action": action,
            "data": data
        }
        try:
            with open(self.audit_log_path, "a") as f:
                import json; f.write(json.dumps(entry) + "\n")
        except Exception as e:
            self._log.error(f"[UpgradeDownloader] Audit log failed: {e}")

    def _alert(self, event: str, data: dict):
        if self.alert_cb:
            try:
                self.alert_cb(event, data)
            except Exception as e:
                self._log.error(f"[UpgradeDownloader] Alert callback failed: {e}")

    def _metrics(self, metric: str, value: float):
        if self.metrics_cb:
            self.metrics_cb(metric, value)

    def _explain(self, info: Dict[str, Any]):
        if self.explainability_cb:
            self.explainability_cb(info)

    def download(self) -> bool:
        """Downloads the upgrade ZIP with hooks, retries, audit, and alerts."""
        if self.pre_download_hook:
            self.pre_download_hook(self.url)
        retries = 0
        while retries <= self.max_retries:
            try:
                response = requests.get(self.url, stream=True, timeout=30)
                if response.status_code == 200:
                    with open(self.save_path, "wb") as f:
                        for chunk in response.iter_content(chunk_size=8192):
                            f.write(chunk)
                    self._log.info(f"[UpgradeDownloader] Downloaded: {self.url} -> {self.save_path}")
                    self._audit("downloaded", {"url": self.url, "save_path": self.save_path})
                    if self.signature_check_cb and not self.signature_check_cb(self.save_path):
                        self._log.warning("[UpgradeDownloader] Signature check failed.")
                        self._audit("signature_failed", {"file": self.save_path})
                        self._alert("signature_failed", {"file": self.save_path})
                        if self.post_download_hook:
                            self.post_download_hook(self.save_path, False)
                        return False
                    if self.post_download_hook:
                        self.post_download_hook(self.save_path, True)
                    self._metrics("upgrade_download_success", time.time())
                    self._explain({"action": "download", "url": self.url, "save_path": self.save_path})
                    return True
                else:
                    self._log.warning(f"[UpgradeDownloader] Download failed ({response.status_code}): {self.url}")
            except Exception as e:
                self._log.error(f"[UpgradeDownloader] Download error: {e}")
                self._alert("download_failed", {"url": self.url, "error": str(e)})
            retries += 1
            time.sleep(self.retry_delay)
        self._audit("download_failed", {"url": self.url})
        if self.post_download_hook:
            self.post_download_hook(self.save_path, False)
        return False

    def extract(self, extract_to: str) -> bool:
        """Extracts the downloaded ZIP with hooks, audit, and alerts."""
        if self.pre_extract_hook:
            self.pre_extract_hook(self.save_path)
        if not os.path.exists(self.save_path):
            self._log.warning(f"[UpgradeDownloader] File not found for extraction: {self.save_path}")
            self._audit("extract_failed", {"file": self.save_path, "reason": "not_found"})
            if self.post_extract_hook:
                self.post_extract_hook(self.save_path, False)
            return False
        try:
            with zipfile.ZipFile(self.save_path, 'r') as zip_ref:
                zip_ref.extractall(extract_to)
            self._log.info(f"[UpgradeDownloader] Extracted: {self.save_path} -> {extract_to}")
            self._audit("extracted", {"zip_path": self.save_path, "extract_to": extract_to})
            if self.post_extract_hook:
                self.post_extract_hook(self.save_path, True)
            self._metrics("upgrade_extract_success", time.time())
            self._explain({"action": "extract", "zip_path": self.save_path, "extract_to": extract_to})
            return True
        except Exception as e:
            self._log.error(f"[UpgradeDownloader] Extraction error: {e}")
            self._audit("extract_failed", {"zip_path": self.save_path, "error": str(e)})
            self._alert("extract_failed", {"zip_path": self.save_path, "error": str(e)})
            if self.post_extract_hook:
                self.post_extract_hook(self.save_path, False)
            return False

# For backwards compatibility:
def extract_upgrade(zip_path: str, extract_to: str):
    """Vivian-style extraction with audit, no hooks."""
    udl = UpgradeDownloader(url="", save_path=zip_path)
    return udl.extract(extract_to)