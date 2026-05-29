import smtplib, os, sys
from email.mime.text import MIMEText

path = sys.argv[1] if len(sys.argv) > 1 else "COMPLETION_REPORT.md"
with open(path, encoding="utf-8") as f:
    body = f.read()

msg = MIMEText(body)
msg["Subject"] = "[SlideAtlas] 작업 완료 보고서"
msg["From"] = os.environ["GMAIL_USER"]
msg["To"]   = os.environ["GMAIL_USER"]

with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
    s.login(os.environ["GMAIL_USER"], os.environ["GMAIL_APP_PW"])
    s.send_message(msg)
print("report sent")
