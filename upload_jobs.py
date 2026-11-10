import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor


class UploadJobs:
    def __init__(self, workers=2, retention_seconds=3600):
        self._executor = ThreadPoolExecutor(
            max_workers=workers, thread_name_prefix="pramana-ingest"
        )
        self._jobs = {}
        self._lock = threading.Lock()
        self._retention_seconds = retention_seconds

    def submit(self, worker, *args):
        job_id = uuid.uuid4().hex
        with self._lock:
            self._prune()
            self._jobs[job_id] = {
                "job_id": job_id,
                "status": "queued",
                "created_at": time.time(),
            }
        self._executor.submit(self._run, job_id, worker, args)
        return job_id

    def _run(self, job_id, worker, args):
        with self._lock:
            self._jobs[job_id]["status"] = "processing"
        try:
            result = worker(*args)
            with self._lock:
                self._jobs[job_id].update(status="complete", result=result)
        except Exception as error:
            with self._lock:
                self._jobs[job_id].update(status="failed", error=str(error))

    def get(self, job_id):
        with self._lock:
            self._prune()
            job = self._jobs.get(job_id)
            return dict(job) if job else None

    def _prune(self):
        cutoff = time.time() - self._retention_seconds
        expired = [
            job_id
            for job_id, job in self._jobs.items()
            if job["created_at"] < cutoff
            and job["status"] in {"complete", "failed"}
        ]
        for job_id in expired:
            del self._jobs[job_id]


upload_jobs = UploadJobs()
