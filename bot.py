import os
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from bs4 import BeautifulSoup

TOKEN = os.getenv("BOT_TOKEN")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Namaste! Mujhe koi `.html` file bhejo, main text extract karke bhej dunga.")

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    document = update.message.document
    
    if not document.file_name.endswith('.html'):
        await update.message.reply_text("Kripya sirf `.html` extension wali file hi bhejein.")
        return

    await update.message.reply_text("File process ho rahi hai, thoda intezar karein...")

    file = await context.bot.get_file(document.file_id)
    file_path = f"temp_{document.file_name}"
    await file.download_to_drive(file_path)

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            html_content = f.read()

        soup = BeautifulSoup(html_content, 'html.parser')
        
        for script in soup(["script", "style"]):
            script.extract()

        extracted_text = soup.get_text(separator='\n').strip()

        if len(extracted_text) == 0:
            await update.message.reply_text("Is HTML file mein koi text nahi mila.")
        elif len(extracted_text) > 4000:
            output_file = "extracted_text.txt"
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(extracted_text)
            await update.message.reply_document(document=open(output_file, 'rb'), caption="Extracted Text File:")
            os.remove(output_file)
        else:
            await update.message.reply_text(f"**Extracted Text:**\n\n{extracted_text}", parse_mode="Markdown")

    except Exception as e:
        await update.message.reply_text(f"Error: {str(e)}")
    
    if os.path.exists(file_path):
        os.remove(file_path)

if __name__ == '__main__':
    app = ApplicationBuilder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))

    print("Bot running...")
    app.run_polling()
  
