# from dotenv import load_dotenv
# import os
# from openai import OpenAI

# # Load environment variables from .env
# load_dotenv()

# client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# response = client.audio.speech.create(
#     model="gpt-4o-mini-tts",   # TTS model
#     voice="alloy",             # Try different voices: alloy, verse, sage, charlie...
#     input="Hello Vaishnavi, testing this voice for your agent use case."
# )

# # Save audio correctly
# with open("alloy_test_voice.mp3", "wb") as f:
#     f.write(response.read())   # <-- use .read() to get raw bytes

# print("Voice sample saved as test_voice.mp3")

import asyncio
import aiosmtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from app.config import settings

from dotenv import load_dotenv
load_dotenv()


async def test_gmail_smtp():
    print("\n=== GMAIL SMTP TEST ===")
    print("SMTP_HOST:", settings.SMTP_HOST)
    print("SMTP_PORT:", settings.SMTP_PORT)
    print("SMTP_USER:", settings.SMTP_USER)

    try:
        message = MIMEMultipart()
        message["From"] = settings.EMAIL_FROM
        message["To"] = settings.SMTP_USER
        message["Subject"] = "Gmail SMTP Test"
        message.attach(MIMEText("This is a test email from AADOS backend.", "plain"))

        print("\nConnecting & sending...")

        await aiosmtplib.send(
            message,
            hostname=settings.SMTP_HOST,
            port=settings.SMTP_PORT,
            username=settings.SMTP_USER,
            password=settings.SMTP_PASSWORD,
            start_tls=True,
        )

        print("\n=== SUCCESS ✅ Email Delivered ===")
        return True

    except Exception as e:
        print("\n=== ERROR ❌ ===")
        print(type(e).__name__)
        print(str(e))
        return False


if __name__ == "__main__":
    asyncio.run(test_gmail_smtp())
