from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import httpx
import sqlite3
import random
import smtplib
from email.mime.text import MIMEText
from pydantic import BaseModel

app = FastAPI()

# Database connection
def get_db_connection():
    conn = sqlite3.connect('database.db')  # replace with your actual database
    conn.row_factory = sqlite3.Row
    return conn

# Webhook Verification
@app.get("/webhook")
async def webhook_verification(hub_verify_token: str, hub_challenge: str):
    verify_token = "YOUR_VERIFY_TOKEN"
    if hub_verify_token == verify_token:
        return JSONResponse(content={"hub.challenge": hub_challenge})
    return JSONResponse(content={"message": "Verification failed"}, status_code=400)

# Models for the message payload
class Message(BaseModel):
    entry: list

@app.post("/webhook")
async def handle_message(request: Request, message: Message):
    input_data = await request.json()

    # Default response text
    response_text = "Invalid input. Please type 'help' to know available commands."

    # Extract message details
    if input_data['entry'][0]['changes'][0]['value'].get('messages'):
        message_data = input_data['entry'][0]['changes'][0]['value']['messages'][0]
        from_number = message_data['from']
        user_msg = ""

        if message_data['type'] == 'button':
            payload = message_data['button']['payload']
            if payload == 'status':
                user_msg = 'status'
        elif message_data['type'] == 'text':
            user_msg = message_data['text']['body'].lower().strip()

        # Auth check in database
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM authentication WHERE mobile_number=? AND status='active'", (from_number,))
        user_data = cursor.fetchone()

        if user_data:
            # Fetch Workday Data
            url = "https://wd5-impl-services1.workday.com/ccx/service/customreport2/datastax/isu_bizapps/Employee_Web_Data"
            params = {
                'Employee_ID': '1665',
                'format': 'simplexml'
            }
            async with httpx.AsyncClient() as client:
                response = await client.get(url, params=params, auth=("isu_bizapps", "Work@123"))
            xml_data = response.text
            # Parse XML and extract data (using libraries like xml.etree.ElementTree or lxml)
            # Example placeholders for Workday data
            name = "John Doe"
            employee_id = "1665"
            leave_balance = "10"

            if user_msg == 'status':
                response_text = f"🧾 *Leave Balance*\nName: {name}\nEmployee ID: {employee_id}\nLeave Balance: {leave_balance} days"
            elif user_msg == 'help':
                response_text = "🤖 Available Commands:\n• status – Get leave balance\n• empid – Show your Employee ID\n• help – Show this menu"
            elif user_msg == 'empid':
                response_text = f"🆔 Your Employee ID is: {employee_id}"
            else:
                response_text = "Invalid command. Type 'help' for options."

        else:
            # Email OTP Flow for unverified user
            cursor.execute("SELECT * FROM authentication WHERE mobile_number=? AND status='unactive'", (from_number,))
            existing_otp = '000000'
            unverified_user = cursor.fetchone()
            if unverified_user:
                existing_otp = unverified_user['otp']

            if '@' in user_msg:  # Email entered
                otp = random.randint(100000, 999999)
                # Send OTP via email (example using SMTP)
                msg = MIMEText(f"Your OTP is: {otp}")
                msg['Subject'] = 'Your OTP'
                msg['From'] = "your-email@example.com"
                msg['To'] = user_msg

                # Assuming an SMTP server setup
                with smtplib.SMTP('smtp.example.com') as server:
                    server.login("your-email@example.com", "your-email-password")
                    server.sendmail(msg['From'], [msg['To']], msg.as_string())

                response_text = f"📧 OTP sent to *{user_msg}*. Reply with the OTP to authenticate."

                if unverified_user:
                    cursor.execute("UPDATE authentication SET otp=? WHERE mobile_number=?", (otp, from_number))
                else:
                    cursor.execute("INSERT INTO authentication (mobile_number, otp, status) VALUES (?, ?, 'unactive')", (from_number, otp))
                conn.commit()

            elif user_msg == existing_otp:
                cursor.execute("UPDATE authentication SET status='active' WHERE mobile_number=?", (from_number,))
                response_text = "✅ Authentication successful! Type *help* for available commands."
                conn.commit()

            else:
                response_text = "🔐 Please provide your email address for OTP-based authentication."

        conn.close()

    # Send WhatsApp response
    access_token = "YOUR_ACCESS_TOKEN"
    phone_number_id = "YOUR_PHONE_NUMBER_ID"

    payload = {
        "messaging_product": "whatsapp",
        "to": from_number,
        "type": "text",
        "text": {"body": response_text}
    }

    async with httpx.AsyncClient() as client:
        await client.post(
            f"https://graph.facebook.com/v22.0/{phone_number_id}/messages",
            headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
            json=payload
        )

    return JSONResponse(content={"message": "Message processed"}, status_code=200)
