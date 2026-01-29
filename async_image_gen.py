#!/usr/bin/env python
"""
Async Image Generation Module
-----------------------------
Provides concurrent image generation using ThreadPoolExecutor.
Images are generated in background threads while text generation continues.
"""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, Future
from dataclasses import dataclass, field
from pathlib import Path
from threading import Lock
from typing import Dict, List, Optional, Tuple, Callable

from image_gen import generate_image, save_image

logger = logging.getLogger(__name__)


@dataclass
class ImageTask:
    """Represents a pending or completed image generation task."""
    task_type: str  # "cover" or "chapter"
    chapter_idx: Optional[int]  # None for cover, 0-indexed for chapters
    prompt: str
    output_path: Path
    future: Optional[Future] = None
    completed: bool = False
    image_path: Optional[str] = None
    error: Optional[str] = None


class ImageGenerationQueue:
    """
    Manages concurrent image generation with ThreadPoolExecutor.

    Usage:
        queue = ImageGenerationQueue(images_dir, flux_model)

        # Submit images (non-blocking)
        queue.submit_cover(title, concept)
        queue.submit_chapter(0, novel_title, chapter_title, chapter_excerpt)

        # Periodically collect completed images
        completed = queue.collect_completed()
        for task in completed:
            if task.image_path:
                # Update state with task.image_path
            elif task.error:
                # Handle error

        # At end, wait for all remaining images
        remaining = queue.wait_all()

        # Always shutdown when done
        queue.shutdown()
    """

    def __init__(
        self,
        images_dir: Path,
        flux_model: str,
        max_workers: int = 2,
        on_complete: Optional[Callable[[ImageTask], None]] = None
    ):
        """
        Initialize the image generation queue.

        Args:
            images_dir: Directory to save generated images
            flux_model: FLUX model identifier for OpenRouter
            max_workers: Maximum concurrent image generations (default: 2)
            on_complete: Optional callback when an image completes
        """
        self.images_dir = images_dir
        self.flux_model = flux_model
        self.on_complete = on_complete
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        self._tasks: Dict[str, ImageTask] = {}  # key: "cover" or "chapter_N"
        self._lock = Lock()
        self._shutdown = False

        logger.info(f"ImageGenerationQueue initialized with {max_workers} workers")

    def _generate_and_save(self, task: ImageTask) -> ImageTask:
        """
        Generate and save an image. Called in worker thread.

        Returns the task with updated completion status.
        """
        try:
            logger.info(f"Generating {task.task_type} image" +
                       (f" for chapter {task.chapter_idx + 1}" if task.chapter_idx is not None else ""))

            image_bytes, ext = generate_image(task.prompt, self.flux_model)

            # Update output path with correct extension
            output_path = task.output_path.with_suffix(f".{ext}")
            save_image(image_bytes, output_path)

            task.image_path = str(output_path)
            task.completed = True
            logger.info(f"Saved {task.task_type} image to {output_path}")

        except Exception as e:
            task.error = str(e)
            task.completed = True
            logger.warning(f"Failed to generate {task.task_type} image: {e}")

        return task

    def submit_cover(self, title: str, concept: str) -> None:
        """
        Submit cover image generation (non-blocking).

        Args:
            title: Novel title
            concept: Novel concept/premise
        """
        if self._shutdown:
            logger.warning("Cannot submit: queue is shutdown")
            return

        from image_gen import generate_cover_prompt

        prompt = generate_cover_prompt(title, concept)
        output_path = self.images_dir / "cover.png"  # Extension updated on save

        task = ImageTask(
            task_type="cover",
            chapter_idx=None,
            prompt=prompt,
            output_path=output_path
        )

        with self._lock:
            task.future = self._executor.submit(self._generate_and_save, task)
            self._tasks["cover"] = task

        logger.info("Submitted cover image generation")

    def submit_chapter(
        self,
        chapter_idx: int,
        novel_title: str,
        chapter_title: str,
        chapter_excerpt: str
    ) -> None:
        """
        Submit chapter image generation (non-blocking).

        Args:
            chapter_idx: 0-indexed chapter number
            novel_title: Novel title
            chapter_title: Chapter title
            chapter_excerpt: Beginning of chapter content for context
        """
        if self._shutdown:
            logger.warning("Cannot submit: queue is shutdown")
            return

        from image_gen import generate_chapter_prompt

        prompt = generate_chapter_prompt(novel_title, chapter_title, chapter_excerpt)
        output_path = self.images_dir / f"chapter_{chapter_idx + 1:02d}.png"

        task = ImageTask(
            task_type="chapter",
            chapter_idx=chapter_idx,
            prompt=prompt,
            output_path=output_path
        )

        with self._lock:
            task.future = self._executor.submit(self._generate_and_save, task)
            self._tasks[f"chapter_{chapter_idx}"] = task

        logger.info(f"Submitted chapter {chapter_idx + 1} image generation")

    def collect_completed(self) -> List[ImageTask]:
        """
        Collect all completed image tasks (non-blocking).

        Returns list of completed tasks. Each task has either:
        - image_path set (success)
        - error set (failure)

        Completed tasks are removed from the queue.
        """
        completed = []

        with self._lock:
            keys_to_remove = []

            for key, task in self._tasks.items():
                if task.future and task.future.done():
                    try:
                        # Get result to propagate any exceptions
                        result = task.future.result(timeout=0)
                        # Task was updated in _generate_and_save
                    except Exception as e:
                        task.error = str(e)
                        task.completed = True

                    completed.append(task)
                    keys_to_remove.append(key)

                    # Call completion callback if set
                    if self.on_complete:
                        try:
                            self.on_complete(task)
                        except Exception as e:
                            logger.warning(f"on_complete callback failed: {e}")

            for key in keys_to_remove:
                del self._tasks[key]

        if completed:
            logger.info(f"Collected {len(completed)} completed image(s)")

        return completed

    def wait_all(self, timeout: Optional[float] = None) -> List[ImageTask]:
        """
        Wait for all pending images to complete.

        Args:
            timeout: Maximum seconds to wait (None = wait forever)

        Returns list of all completed tasks.
        """
        completed = []

        with self._lock:
            pending_tasks = list(self._tasks.items())

        for key, task in pending_tasks:
            if task.future:
                try:
                    task.future.result(timeout=timeout)
                except Exception as e:
                    task.error = str(e)
                    task.completed = True

                completed.append(task)

                if self.on_complete:
                    try:
                        self.on_complete(task)
                    except Exception as e:
                        logger.warning(f"on_complete callback failed: {e}")

        # Clear all tasks
        with self._lock:
            self._tasks.clear()

        logger.info(f"Waited for {len(completed)} image(s) to complete")
        return completed

    def pending_count(self) -> int:
        """Return number of pending (not yet completed) image tasks."""
        with self._lock:
            return sum(1 for t in self._tasks.values() if not t.completed)

    def get_pending_info(self) -> List[Dict]:
        """Return info about pending tasks for UI display."""
        with self._lock:
            return [
                {
                    "type": task.task_type,
                    "chapter_idx": task.chapter_idx,
                    "completed": task.completed
                }
                for task in self._tasks.values()
            ]

    def shutdown(self, wait: bool = True) -> None:
        """
        Shutdown the executor.

        Args:
            wait: If True, wait for pending tasks to complete
        """
        self._shutdown = True
        self._executor.shutdown(wait=wait)
        logger.info("ImageGenerationQueue shutdown complete")
