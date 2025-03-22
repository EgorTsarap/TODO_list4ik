import asyncio
from datetime import datetime, timedelta

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
from pymongo import MongoClient
from bson.objectid import ObjectId

from tasks import schedule_reminder, schedule_deadline_extension

# MongoDB подключение
client = MongoClient('localhost', 27017)
db = client['task_manager']
tasks_collection = db['tasks']

TOKEN = '7767786459:AAFU8doopUlrQ5IrYQ76xOAj-pe6X4EWPW8'


def get_main_keyboard():
    return ReplyKeyboardMarkup(
        [
            ["Добавить задачу"],
            ["Список задач"],
            ["Удалить задачи по дате"],
            ["Проверить время"]
        ],
        resize_keyboard=True
    )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Добро пожаловать в ToDo Bot!", reply_markup=get_main_keyboard())


async def add_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        'Введите задачу в формате:\nТекст задачи 2025-03-20 14:30'
    )
    context.user_data['action'] = 'add_task'


async def list_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    tasks = list(tasks_collection.find({'user_id': user_id}))

    if not tasks:
        await update.message.reply_text('У вас нет задач.')
        return

    for task in tasks:
        status = '✅' if task['completed'] else '❌'
        task_text = f"{status} {task['task_text']} (до {task['deadline'].strftime('%Y-%m-%d %H:%M')})"
        keyboard = [
            [
                InlineKeyboardButton("Изменить", callback_data=f"edit_{task['_id']}"),
                InlineKeyboardButton("Удалить", callback_data=f"delete_{task['_id']}"),
                InlineKeyboardButton("Выполнено", callback_data=f"complete_{task['_id']}")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(task_text, reply_markup=reply_markup)


async def delete_tasks_by_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Введите дату в формате YYYY-MM-DD:")
    context.user_data['action'] = 'delete_by_date'


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    task_id = ObjectId(data.split('_')[1])

    if data.startswith('edit_'):
        await query.message.reply_text("Введите новый текст задачи:")
        context.user_data['action'] = f'edit_{task_id}'
    elif data.startswith('delete_'):
        tasks_collection.delete_one({'_id': task_id})
        await query.message.reply_text("Задача удалена.")
    elif data.startswith('complete_'):
        tasks_collection.update_one({'_id': task_id}, {'$set': {'completed': True}})
        await query.message.reply_text("Задача отмечена как выполненная.")


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    text = update.message.text
    action = context.user_data.get('action')

    if action == 'add_task':
        try:
            task_text, deadline_str, time_str = text.rsplit(' ', 2)
            deadline = datetime.strptime(f"{deadline_str} {time_str}", '%Y-%m-%d %H:%M')

            task = {
                'user_id': user_id,
                'task_text': task_text,
                'deadline': deadline,
                'completed': False
            }
            result = tasks_collection.insert_one(task)

            # Планируем напоминание и продление
            schedule_reminder.apply_async((str(result.inserted_id),), eta=deadline - timedelta(minutes=30))
            schedule_deadline_extension.apply_async((str(result.inserted_id),), eta=deadline + timedelta(seconds=5))

            await update.message.reply_text(f"Задача добавлена! Дедлайн: {deadline.strftime('%Y-%m-%d %H:%M')}")
        except Exception as e:
            await update.message.reply_text(f"Ошибка: {e}\nФормат: Текст задачи 2025-03-20 14:30")
        finally:
            context.user_data['action'] = None

    elif action and action.startswith('edit_'):
        task_id = ObjectId(action.split('_')[1])
        result = tasks_collection.update_one({'_id': task_id, 'user_id': user_id}, {'$set': {'task_text': text}})
        if result.modified_count > 0:
            await update.message.reply_text("Задача обновлена.")
        else:
            await update.message.reply_text("Задача не найдена.")
        context.user_data['action'] = None

    elif action == 'delete_by_date':
        try:
            date = datetime.strptime(text, '%Y-%m-%d')
            start = datetime.combine(date, datetime.min.time())
            end = datetime.combine(date, datetime.max.time())

            result = tasks_collection.delete_many({
                'user_id': user_id,
                'deadline': {'$gte': start, '$lte': end}
            })

            await update.message.reply_text(f"Удалено задач: {result.deleted_count}")
        except Exception as e:
            await update.message.reply_text(f"Ошибка: {e}\nФормат даты: YYYY-MM-DD")
        finally:
            context.user_data['action'] = None


async def check_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    tasks = list(tasks_collection.find({'user_id': user_id}))

    if not tasks:
        await update.message.reply_text('У вас нет задач.')
        return

    now = datetime.now()
    for task in tasks:
        deadline = task['deadline']
        time_left = deadline - now

        if time_left.total_seconds() < 0:
            await update.message.reply_text(f"Задача '{task['task_text']}' ПРОСРОЧЕНА!")
        else:
            days = time_left.days
            hours = time_left.seconds // 3600
            minutes = (time_left.seconds % 3600) // 60
            await update.message.reply_text(
                f"Задача: {task['task_text']}\nОсталось: {days} дн {hours} ч {minutes} мин"
            )


def main():
    application = Application.builder().token(TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.Text("Добавить задачу"), add_task))
    application.add_handler(MessageHandler(filters.Text("Список задач"), list_tasks))
    application.add_handler(MessageHandler(filters.Text("Удалить задачи по дате"), delete_tasks_by_date))
    application.add_handler(MessageHandler(filters.Text("Проверить время"), check_time))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    application.run_polling()


if __name__ == '__main__':
    main()
