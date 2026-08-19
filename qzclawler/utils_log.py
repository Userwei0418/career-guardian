
from email.mime.text import MIMEText
import smtplib
from utils import get_local_ip

#发送错误邮件
def send_email(_content): 
    sender = '5790712@qq.com'
    receiver = 'chuziguang@quanzhi.com' 
    cc_receivers = []
    all_receivers = [receiver] + cc_receivers
    password = 'arqloupmitvqbiic'

    ip = get_local_ip()
    msg = MIMEText(f'异常邮件<br>{_content}', 'html', 'utf-8')
    msg['Subject'] = f'数据爬虫异常邮件,来自{ip}\n'
    msg['From'] = sender
    msg['To'] = receiver
    msg['CC'] = ', '.join(cc_receivers)

    try:
        server = smtplib.SMTP_SSL('smtp.qq.com', 465)
        server.login(sender, password)
        server.sendmail(sender, all_receivers, msg.as_string()) 
        server.quit()  # 关闭连接
    except Exception as e:
        print(f'邮件发送失败: {e}')