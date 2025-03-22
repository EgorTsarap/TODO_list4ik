from celery import Celery
from pymongo import MongoClient
from telegram import Bot
from datetime import datetime, timedelta
from bson.objectid import ObjectId


client = MongoClient('localhost', 27017)
db = client['task_manager']
tasks_collection = db['tasks']

celery_app = Celery('tasks', broker='redis://localhost:6379/0')

BOT_TOKEN = '7767786459:AAFU8doopUlrQ5IrYQ76xOAj-pe6X4EWPW8'
bot = Bot(BOT_TOKEN)


@celery_app.task
def schedule_reminder(task_id):
    task = tasks_collection.find_one({'_id': ObjectId(task_id)})

    if task and not task['completed']:
        user_id = task['user_id']
        message = f"Напоминание! Скоро дедлайн задачи:\n{task['task_text']}\nДо {task['deadline'].strftime('%Y-%m-%d %H:%M')}"
        bot.send_message(chat_id=user_id, text=message)


@celery_app.task
def schedule_deadline_extension(task_id):
    task = tasks_collection.find_one({'_id': ObjectId(task_id)})

    if task and not task['completed']:
        now = datetime.now()
        if task['deadline'] < now:
            new_deadline = now + timedelta(days=1)
            tasks_collection.update_one({'_id': task['_id']}, {'$set': {'deadline': new_deadline}})

            user_id = task['user_id']
            message = f"Дедлайн задачи '{task['task_text']}' просрочен!\nОн продлён до {new_deadline.strftime('%Y-%m-%d %H:%M')}."
            bot.send_message(chat_id=user_id, text=message)
