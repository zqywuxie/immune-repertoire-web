import smtplib
from email.mime.text import MIMEText
from appone.models.EmailCode import EmailCode
from_address = '2996847277@qq.com'
wand = "meckegfhwmefdgbj"



def create_code():
    import random
    code = ''
    for i in range(6):
        code += str(random.choice([random.randint(0, 9), chr(random.randint(97, 122)), chr(random.randint(65, 90))]))
    return code


def send_email(to_address):
    code = create_code()
    message = MIMEText(f"验证码为 {code},有效期为5分钟", "html", 'utf-8')
    message['From'] = from_address
    message['To'] = to_address
    message['subject'] = '验证码'
    email = smtplib.SMTP_SSL('smtp.qq.com', 465, 'utf-8')
    email.login(from_address, wand)
    email.sendmail(from_address, to_address, message.as_string())
    EmailCode.objects.create(code=code, email=to_address)


