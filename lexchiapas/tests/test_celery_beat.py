"""El Beat no debe reingerir leyes solo; el vigilante semanal si esta programado."""

from app.workers.celery_app import celery_app


def test_beat_does_not_schedule_automatic_law_reingestion():
    tasks = {entry["task"] for entry in celery_app.conf.beat_schedule.values()}
    assert "app.workers.update_tasks.check_for_law_updates" not in tasks


def test_beat_schedules_the_weekly_law_watcher_and_the_canaries():
    tasks = {entry["task"] for entry in celery_app.conf.beat_schedule.values()}
    assert "app.workers.update_watcher.law_update_watcher" in tasks
    assert "app.workers.alerting_tasks.health_canary" in tasks
    assert "app.workers.alerting_tasks.llm_models_canary" in tasks


def test_reingestion_task_is_still_registered_for_manual_runs():
    assert "app.workers.update_tasks.check_for_law_updates" in celery_app.tasks
