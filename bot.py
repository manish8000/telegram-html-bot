import os
import logging
import re
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from bs4 import BeautifulSoup

# Logging setup
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

TOKEN = os.getenv("BOT_TOKEN")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message:
        await update.message.reply_text("Namaste! Mujhe koi `.html` file bhejo, main usme se saare Video aur PDF Links Title ke saath extract kar dunga.")

async def process_html_file(bot, chat_id, document):
    if not document.file_name.lower().endswith('.html'):
        await bot.send_message(chat_id=chat_id, text="Kripya sirf `.html` extension wali file hi bhejein.")
        return

    await bot.send_message(chat_id=chat_id, text="HTML File scan ho rahi hai, Video aur PDF links dhoondhe ja rahe hain...")

    file = await bot.get_file(document.file_id)
    file_path = f"temp_{document.file_name}"
    await file.download_to_drive(file_path)

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            html_content = f.read()

        soup = BeautifulSoup(html_content, 'html.parser')
        
        extracted_data = []

        # 1. Tags scan karein (a, video, iframe, source)
        tags = soup.find_all(['a', 'video', 'source', 'iframe'])

        for tag in tags:
            url = tag.get('href') or tag.get('src')
            if not url:
                continue

            # Title extraction
            title = tag.get_text().strip() or tag.get('title') or tag.get('alt')
            
            # Agar parent/container mein koi text mile
            if not title and tag.parent:
                title = tag.parent.get_text().strip()
                
            if not title:
                title = "Untitled Resource"

            # Clean up multi-line title
            title = re.sub(r'\s+', ' ', title)

            # Filter Videos & PDFs
            url_lower = url.lower()
            is_video = any(ext in url_lower for ext in ['.mp4', '.m3u8', '.mkv', 'youtube.com', 'youtu.be', 'vimeo.com', 'drive.google.com'])
            is_pdf = '.pdf' in url_lower or 'drive.google.com/file' in url_lower

            if is_video:
                extracted_data.append(f"🎥 **Title:** {title}\n🔗 **Video URL:** {url}\n")
            elif is_pdf:
                extracted_data.append(f"📄 **Title:** {title}\n🔗 **PDF URL:** {url}\n")

        # Result formatting
        if not extracted_data:
            response_text = "Is HTML file mein koi Video ya PDF link nahi mila."
        else:
            response_text = f" Total {len(extracted_data)} Links Mile:\n\n" + "\n-------------------\n\n".join(extracted_data)

        # Output messaging
        if len(response_text) > 4000:
            output_file = "Extracted_Links.txt"
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(response_text.replace('**', ''))
            await bot.send_document(chat_id=chat_id, document=open(output_file, 'rb'), caption=" Links ki complete list file mein hai:")
            if os.path.exists(output_file):
                os.remove(output_file)
        else:
            await bot.send_message(chat_id=chat_id, text=response_text, parse_mode="Markdown")

    except Exception as e:
        await bot.send_message(chat_id=chat_id, text=f"Error: {str(e)}")
    
    if os.path.exists(file_path):
        os.remove(file_path)

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message and update.message.document:
        await process_html_file(context.bot, update.message.chat_id, update.message.document)
    elif update.channel_post and update.channel_post.document:
        await process_html_file(context.bot, update.channel_post.chat_id, update.channel_post.document)

if __name__ == '__main__':
    if not TOKEN:
        raise ValueError("BOT_TOKEN environment variable is missing!")
        
    app = ApplicationBuilder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))

    print("Bot running...")
    app.run_polling(drop_pending_updates=True)
                                
