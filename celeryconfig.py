from celery.schedules import crontab

broker_url = 'redis://localhost:6379/0'
result_backend = 'redis://localhost:6379/0'

beat_schedule = {
    'daily-task-notification': {
        'task': 'tasks.notify_upcoming_deadlines',
        'schedule': crontab(hour=9, minute=0),
    },
}

timezone = 'Europe/Moscow'
