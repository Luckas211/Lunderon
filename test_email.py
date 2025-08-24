import smtplib
# ADICIONE ESTES IMPORTS para lidar com acentuação
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

# --- CONFIGURE AQUI ---
remetente = "ledark.sac@gmail.com"
senha_app = "uxui ilqx uzbf eadq"  # Sua senha de app de 16 dígitos
destinatario = "ledark.sac@gmail.com" # Pode enviar para você mesmo para testar
# --------------------

servidor_smtp = "smtp.gmail.com"
porta = 587

try:
    print("Tentando conectar ao servidor do Gmail...")
    server = smtplib.SMTP(servidor_smtp, porta)
    server.starttls()
    
    print("Conexão estabelecida. Fazendo login...")
    server.login(remetente, senha_app)
    
    print("Login bem-sucedido. Montando e-mail...")
    
    # --- CÓDIGO ALTERADO PARA USAR UTF-8 ---
    # Cria o objeto do e-mail
    msg = MIMEMultipart()
    msg['From'] = remetente
    msg['To'] = destinatario
    msg['Subject'] = "Teste de E-mail Direto do Python"
    
    # Corpo do e-mail com acentuação
    corpo = "Se você recebeu este e-mail, a conexão SMTP está funcionando!"
    
    # Anexa o corpo ao e-mail, especificando que é em formato UTF-8
    msg.attach(MIMEText(corpo, 'plain', 'utf-8'))
    # ----------------------------------------
    
    print("Enviando e-mail...")
    server.sendmail(remetente, destinatario, msg.as_string())
    print("✅ E-mail enviado com sucesso!")
    
except Exception as e:
    print("\n❌ Ocorreu um erro:")
    print(e)
    
finally:
    try:
        server.quit()
        print("Conexão com o servidor fechada.")
    except:
        pass