import os
import logging
import re
import aiohttp
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from bs4 import BeautifulSoup

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

TOKEN = os.getenv("BOT_TOKEN")

async def download_file(url, file_path):
    """URL se file download karne ka function"""
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            if response.status == 200:
                with open(file_path, 'wb') as f:
                    while True:
                        chunk = await response.content.read(1024 * 1024) # 1MB chunks
                        if not chunk:
                            break
                        f.write(chunk)
                return True
    return False

async def process_html_file(bot, chat_id, document):
    if not document.file_name.lower().endswith('.html'):
        await bot.send_message(chat_id=chat_id, text="⚠️ Kripya sirf `.html` extension wali file hi bhejein.")
        return

    await bot.send_message(chat_id=chat_id, text="🔍 HTML File scan ho rahi hai...")

    file = await bot.get_file(document.file_id)
    html_path = f"temp_{document.file_name}"
    await file.download_to_drive(html_path)

    try:
        with open(html_path, 'r', encoding='utf-8') as f:
            html_content = f.read()

        soup = BeautifulSoup(html_content, 'html.parser')
        tags = soup.find_all(['a', 'video', 'source', 'iframe'])

        media_items = []

        for tag in tags:
            url = tag.get('href') or tag.get('src')
            if not url or not url.startswith('http'):
                continue

            # Title Extract Karein
            title = tag.get_text().strip() or tag.get('title') or tag.get('alt')
            if not title and tag.parent:
                title = tag.parent.get_text().strip()
            if not title:
                title = "Media File"

            title = re.sub(r'\s+', ' ', title)[:100] # Safe length limit

            url_lower = url.lower()
            if any(ext in url_lower for ext in ['.mp4', '.mkv']):
                media_items.append({'type': 'video', 'url': url, 'title': title})
            elif '.pdf' in url_lower:
                media_items.append({'type': 'pdf', 'url': url, 'title': title})

        if not media_items:
            await bot.send_message(chat_id=chat_id, text="❌ Is HTML file mein koi direct `.mp4` ya `.pdf` downloadable links nahi mile.")
            os.remove(html_path)
            return

        await bot.send_message(chat_id=chat_id, text=f"📥 Total {len(media_items)} files mili hain. Download aur Upload process shuru ho raha hai...")

        # Process each media file
        for idx, item in enumerate(media_items, 1):
            file_type = item['type']
            url = item['url']
            title = item['title']

            ext = ".mp4" if file_type == "video" else ".pdf"
            temp_filename = f"downloaded_{idx}{ext}"

            await bot.send_message(chat_id=chat_id, text=f"⏳ [{idx}/{len(media_items)}] Downloading: {title}...")

            success = await download_file(url, temp_filename)

            if success and os.path.exists(temp_filename):
                await bot.send_message(chat_id=chat_id, text=f"📤 Uploading to channel: {title}...")

                with open(temp_filename, 'rb') as f:
                    if file_type == 'video':
                        await bot.send_video(
                            chat_id=chat_id,
                            video=f,
                            caption=f"🎥 **{title}**",
                            parse_mode="Markdown",
                            supports_streaming=True
                        )
                    else:
                        await bot.send_document(
                            chat_id=chat_id,
                            document=f,
                            caption=f"📄 **{title}**",
                            parse_mode="Markdown"
                        )
                os.remove(temp_filename)
            else:
                await bot.send_message(chat_id=chat_id, text=f"❌ Download Fail ho gaya: {title}\n🔗 URL: {url}")

        await bot.send_message(chat_id=chat_id, text="✅ Sabhi files processing poori ho gayi hai!")

    except Exception as e:
        await bot.send_message(chat_id=chat_id, text=f"⚠️ Error aaya: {str(e)}")

    if os.path.exists(html_path):
        os.remove(html_path)

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message and update.message.document:
        await process_html_file(context.bot, update.message.chat_id, update.message.document)
    elif update.channel_post and update.channel_post.document:
        await process_html_file(context.bot, update.channel_post.chat_id, update.channel_post.document)

if __name__ == '__main__':
    if not TOKEN:
        raise ValueError("BOT_TOKEN missing!")

    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))

    print("Bot is running...")
    app.run_polling(drop_pending_updates=True)
    
