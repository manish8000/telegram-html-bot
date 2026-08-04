import os
import logging
import re
import asyncio
import json
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

# 1. START COMMAND
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    await context.bot.send_message(
        chat_id=chat_id,
        text="👋 **नमस्ते!**\n\nमुझे कोई भी टेस्ट सीरीज़ फ़ाइल (.html / .txt / .pdf) भेजें।\n- प्रश्नों को **शुद्ध हिंदी** में एक्सट्रेक्ट किया जाएगा।\n- हर **15 सेकंड** में क्विज़ पोल स्वतः पोस्ट होगा!",
        parse_mode="Markdown"
    )

# 2. File Extractor with Clean Text
def extract_text_from_file(file_path):
    text = ""
    if file_path.endswith('.html'):
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            soup = BeautifulSoup(f.read(), 'html.parser')
            for tag in soup(["script", "style", "nav", "footer", "header"]):
                tag.extract()
            text = soup.get_text(separator=' ')
    else:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            text = f.read()

    # Extra whitespaces ko remove karna
    cleaned_text = re.sub(r'\s+', ' ', text).strip()
    return cleaned_text

# 3. Groq AI Extraction (Strict Native JSON Mode)
async def parse_quiz_with_groq(text_content):
    if not client:
        logging.error("GROQ_API_KEY Missing!")
        return []

    # Chunky text: Max 5000 chars taaki JSON cut na ho
    safe_text = text_content[:5000]

    system_prompt = (
        "You are a quiz extractor. Extract all multiple choice questions from the text and translate EVERYTHING into HINDI (Devanagari script).\n"
        "You MUST reply strictly in JSON format as a JSON Object with a key 'quizzes' containing the array of question objects.\n"
        "Example Schema:\n"
        "{\n"
        '  "quizzes": [\n'
        '    {\n'
        '      "question": "हिंदी में प्रश्न",\n'
        '      "options": ["विकल्प 1", "विकल्प 2", "विकल्प 3", "विकल्प 4"],\n'
        '      "correct_option_id": 0,\n'
        '      "explanation": "हिंदी में व्याख्या"\n'
        '    }\n'
        '  ]\n'
        "}"
    )

    try:
        response = client.chat.completions.create(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Extract quizzes from this content:\n{safe_text}"}
            ],
            model="llama-3.3-70b-versatile",
            response_format={"type": "json_object"},  # Forces valid JSON response
            temperature=0.1
        )

        res_text = response.choices[0].message.content
        data = json.loads(res_text)

        if isinstance(data, dict):
            return data.get("quizzes", [])
        elif isinstance(data, list):
            return data
            
    except Exception as e:
        logging.error(f"Groq Parsing Error: {e}")
        # Fallback regex parsing if JSON has minor syntax issues
        try:
            match = re.search(r'\{.*\}', res_text, re.DOTALL)
            if match:
                data = json.loads(match.group(0))
                return data.get("quizzes", [])
        except Exception as inner_e:
            logging.error(f"Fallback Parse Error: {inner_e}")

    return []

# 4. Document Processing & Quiz Loop
async def process_document(bot, chat_id, document):
    await bot.send_message(chat_id=chat_id, text="📄 फ़ाइल मिल गई है! हिंदी में क्विज़ तैयार किया जा रहा है...")

    file = await bot.get_file(document.file_id)
    file_path = f"temp_{document.file_name}"
    await file.download_to_drive(file_path)

    try:
        text_content = extract_text_from_file(file_path)
        quiz_data = await parse_quiz_with_groq(text_content)

        if not quiz_data:
            await bot.send_message(
                chat_id=chat_id, 
                text="❌ प्रश्न एक्सट्रेक्ट नहीं हो सके। कृपया सुनिश्चित करें कि फ़ाइल में सही टेक्स्ट/HTML सामग्री है और GROQ_API_KEY सही है।"
            )
            if os.path.exists(file_path):
                os.remove(file_path)
            return

        total_q = len(quiz_data)
        await bot.send_message(
            chat_id=chat_id, 
            text=f"🎯 **कुल {total_q} प्रश्न (हिंदी) तैयार हैं!**\n\n⏰ हर **15 सेकंड** में क्विज़ पोस्ट होगा..."
        )

        for idx, q in enumerate(quiz_data, 1):
            question_text = f"[{idx}/{total_q}] {q.get('question', '')}"
            options = [str(opt)[:100] for opt in q.get('options', [])[:10]]

            if not options or len(options) < 2:
                continue

            correct_id = q.get('correct_option_id', 0)
            if not isinstance(correct_id, int) or correct_id >= len(options) or correct_id < 0:
                correct_id = 0

            explanation = str(q.get('explanation', 'सही उत्तर gewählt!'))[:200]

            await bot.send_poll(
                chat_id=chat_id,
                question=question_text[:300],
                options=options,
                type="quiz",
                correct_option_id=correct_id,
                explanation=explanation,
                is_anonymous=True
            )

            # 15 SECONDS DELAY
            if idx < total_q:
                await asyncio.sleep(15)

        await bot.send_message(chat_id=chat_id, text="🎉 **क्विज़ समाप्त हो गया है!**")

    except Exception as e:
        await bot.send_message(chat_id=chat_id, text=f"⚠️ त्रुटि (Error): {str(e)}")

    if os.path.exists(file_path):
        os.remove(file_path)

# 5. Handlers
async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message and update.message.document:
        await process_document(context.bot, update.message.chat_id, update.message.document)
    elif update.channel_post and update.channel_post.document:
        await process_document(context.bot, update.channel_post.chat_id, update.channel_post.document)

if __name__ == '__main__':
    if not TOKEN:
        raise ValueError("BOT_TOKEN Missing!")

    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))

    print("Bot is up and running...")
    app.run_polling(drop_pending_updates=True)
                      
