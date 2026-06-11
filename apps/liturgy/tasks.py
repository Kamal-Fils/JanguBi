import asyncio
import logging
from datetime import date, timedelta

from celery import shared_task
from django.utils import timezone

logger = logging.getLogger(__name__)


@shared_task(name="apps.liturgy.tasks.daily_sync")
def daily_sync_task(date_str: str | None = None, zones: list[str] | None = None):
    from apps.liturgy.services import AelfService  # local import — évite les imports circulaires

    if not date_str:
        date_str = timezone.now().date().isoformat()

    if not zones:
        zones = ["romain"]

    logger.info(f"Starting scheduled daily AELF sync for dates: {date_str} in zones: {zones}")

    for zone in zones:
        try:
            asyncio.run(AelfService.sync_daily_data(date_str, zone))
        except Exception as e:
            logger.error(f"Failed to sync daily data for {date_str} ({zone}): {str(e)}")


@shared_task(name="apps.liturgy.tasks.bulk_import")
def bulk_import_task(start_date_str: str, end_date_str: str, zones: list[str] | None = None):
    """
    Backfills AELF data over a range of dates.
    In production, this could enqueue individual `daily_sync_task` to parallelize work.
    """
    try:
        start_dt = date.fromisoformat(start_date_str)
        end_dt = date.fromisoformat(end_date_str)
    except ValueError:
        logger.error("Invalid date format. Use YYYY-MM-DD.")
        return
        
    if not zones:
        zones = ["romain", "afrique"]

    logger.info(f"Starting bulk AELF sync from {start_date_str} to {end_date_str}")
    
    delta = timedelta(days=1)
    current_dt = start_dt
    
    while current_dt <= end_dt:
        dt_str = current_dt.isoformat()
        logger.info(f"Enqueuing daily sync for {dt_str}")
        
        # Dispatch to queue to avoid a single massive blocking task
        daily_sync_task.delay(dt_str, zones)
        
        current_dt += delta
