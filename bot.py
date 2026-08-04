import os
import logging
import re
import asyncio
import json
import aiohttp
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from bs4 import BeautifulSoup
from groq import Groq

# Logging setup
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

TOKEN = os.getenv("BOT_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None

# 1. START COMMAND (Fixes the NameError)
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    await context.bot.send_message(
        chat_id=chat_id,
        text="👋 **Namaste!**\n\nMujhe koi bhi `.html` ya Text/PDF file bhejo:\n- Media files ko download/upload karega.\n- Test Series/Quizzes ko Groq AI se extract karke har **15 Second** mein post karega!",
        parse_mode="Markdown"
    )

# 2. File Extractor & Helper Functions
def extract_text_from_file(file_path):
    if file_path.endswith('.html'):
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            soup = BeautifulSoup(f.read(), 'html.parser')
            for tag in soup(["script", "style"]):
                tag.extract()
            return soup.get_text(separator='\n')
    else:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            return f.read()

async def parse_quiz_with_groq(text_content):
    if not client:
        logging.error("GROQ_API_KEY Missing!")
        return []

    prompt = f"""
    Extract multiple-choice questions from this text.
    Return ONLY a valid JSON Array. Do NOT use markdown code blocks.
    
    Format:
    [
      {{
        "question": "Question text",
        "options": ["Option 1", "Option 2", "Option 3", "Option 4"],
        "correct_option_id": 0,
        "explanation": "Explanation text (max 200 chars)"
      }}
    ]

    Text:
    {text_content[:12000]}
    """

    try:
        response = client.chat.completions.create(
            messages=[
                {"role": "system", "content": "You are a JSON extractor for Telegram quiz generation."},
                {"role": "user", "content": prompt}
            ],
            model="llama-3.3-70b-versatile",
            temperature=0.2,
        )

        res_text = response.choices[0].message.content
        json_match = re.search(r'\[.*\]', res_text, re.DOTALL)
        if json_match:
            return json.loads(json_match.group(0))
    except Exception as e:
        logging.error(f"Groq API Error: {e}")
    return []

# 3. Process Document Logic
async def process_document(bot, chat_id, document):
    await bot.send_message(chat_id=chat_id, text="📄 Document mil gaya! Process kiya jaa raha hai...")

    file = await bot.get_file(document.file_id)
    file_path = f"temp_{document.file_name}"
    await file.download_to_drive(file_path)

    try:
        text_content = extract_text_from_file(file_path)
        quiz_data = await parse_quiz_with_groq(text_content)

        if not quiz_data:
            await bot.send_message(
                chat_id=chat_id, 
                text="❌ Questions extract nahi ho paaye. Ensure karein ki `GROQ_API_KEY` Railway variables mein add hai."
            )
            if os.path.exists(file_path):
                os.remove(file_path)
            return

        total_q = len(quiz_data)
        await bot.send_message(
            chat_id=chat_id, 
            text=f"🎯 **Total {total_q} Questions Found!**\n\n⏰ Har **15 Seconds** mein quiz post hoga..."
        )

        for idx, q in enumerate(quiz_data, 1):
            question_text = f"[{idx}/{total_q}] {q['question']}"
            options = [str(opt)[:100] for opt in q['options'][:10]]
            correct_id = q.get('correct_option_id', 0)
            
            if not isinstance(correct_id, int) or correct_id >= len(options) or correct_id < 0:
                correct_id = 0

            explanation = str(q.get('explanation', 'Correct option!'))[:200]

            await bot.send_poll(
                chat_id=chat_id,
                question=question_text[:300],
                options=options,
                type="quiz",
                correct_option_id=correct_id,
                explanation=explanation,
                is_anonymous=True
            )

            if idx < total_q:
                await asyncio.sleep(15)

        await bot.send_message(chat_id=chat_id, text="🎉 **Quiz Complete!**")

    except Exception as e:
        await bot.send_message(chat_id=chat_id, text=f"⚠️ Error: {str(e)}")

    if os.path.exists(file_path):
        os.remove(file_path)

# 4. Message Handler
async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message and update.message.document:
        await process_document(context.bot, update.message.chat_id, update.message.document)
    elif update.channel_post and update.channel_post.document:
        await process_document(context.bot, update.channel_post.chat_id, update.channel_post.document)

if __name__ == '__main__':
    if not TOKEN:
        raise ValueError("BOT_TOKEN Variable Missing!")

    app = ApplicationBuilder().token(TOKEN).build()

    # Handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))

    print("Bot is up and running...")
    app.run_polling(drop_pending_updates=True)
    
