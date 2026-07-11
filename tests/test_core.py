"""Unit tests for course tracking state and the bounded async worker pool."""

import asyncio
import sys
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from models.course import TrackedCourse
from services.tracker import CourseTracker
from services.worker_pool import WorkerPool


def make_course() -> TrackedCourse:
    return TrackedCourse(
        code="CS1006301",
        name="Algorithms",
        teacher="Ada",
        lesson_time="Mon 1-2",
        classroom="TR-101",
        remark="",
        enrolled_students=29,
        max_students=30,
        notified=False,
        followers={101},
    )


class WorkerPoolTests(unittest.IsolatedAsyncioTestCase):
    async def test_submit_returns_result_and_reuses_bounded_workers(self):
        pool = WorkerPool(size=2)
        await pool.start()

        async def double(value):
            return value * 2

        try:
            results = await asyncio.gather(*(pool.submit(double, value) for value in range(6)))
            self.assertEqual(results, [0, 2, 4, 6, 8, 10])
            self.assertEqual(len(pool.workers), 2)
        finally:
            await pool.stop()

        self.assertFalse(pool.running)
        self.assertEqual(pool.workers, [])

    async def test_submit_propagates_task_exception(self):
        pool = WorkerPool(size=1)
        await pool.start()

        async def fail():
            raise ValueError("expected failure")

        try:
            with self.assertRaisesRegex(ValueError, "expected failure"):
                await pool.submit(fail)
        finally:
            await pool.stop()


class CourseTrackerTests(unittest.IsolatedAsyncioTestCase):
    async def test_stop_tracking_keeps_course_until_last_follower_is_removed(self):
        messages = []
        tracker = CourseTracker(
            bot=object(),
            guild_channels={},
            worker_pool=WorkerPool(),
            debug_print=messages.append,
        )
        course = make_course()
        course.add_follower(202)

        await tracker.start_tracking(1, course.code, course)

        self.assertFalse(await tracker.stop_tracking(1, course.code, 101))
        self.assertEqual(tracker.get_course(1, course.code).followers, {202})

        self.assertTrue(await tracker.stop_tracking(1, course.code, 202))
        self.assertIsNone(tracker.get_course(1, course.code))
        self.assertTrue(any("完全移除課程" in message for message in messages))

    async def test_clear_all_courses_reports_per_guild_counts(self):
        tracker = CourseTracker(
            bot=object(),
            guild_channels={},
            worker_pool=WorkerPool(),
            debug_print=lambda _message: None,
        )
        await tracker.start_tracking(1, "A", make_course())
        await tracker.start_tracking(2, "B", make_course())

        self.assertEqual(await tracker.clear_all_courses(), {1: 1, 2: 1})
        self.assertEqual(tracker.tracked_courses, {})
