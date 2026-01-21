import redis
import sys

def test_redis_connection(host, port=6379):
    """
    Tenta se conectar a um servidor Redis e reporta o status.
    """
    print(f"Tentando conectar ao Redis em {host}:{port}...")
    try:
        # Tenta criar uma conexão. `socket_connect_timeout` define o tempo de espera.
        r = redis.Redis(
            host=host,
            port=port,
            db=0,
            socket_connect_timeout=5,  # 5 segundos de timeout
            decode_responses=True # Decodificar respostas para string
        )
        
        # O comando PING é uma forma simples de verificar se a conexão está viva.
        response = r.ping()
        
        if response:
            print("\n✅ Conexão com o Redis bem-sucedida!")
            print("   O servidor respondeu ao PING.")
        else:
            print("\n⚠️ Conexão estabelecida, mas o servidor não respondeu ao PING como esperado.")

    except redis.exceptions.ConnectionError as e:
        print(f"\n❌ Erro de Conexão: Não foi possível conectar ao Redis.")
        print(f"   Detalhes: {e}")
        print("\n   Possíveis causas:")
        print("   1. O endereço IP está incorreto ou não é o IP público do servidor.")
        print("   2. O servidor Redis não está em execução na máquina de destino.")
        print("   3. Um firewall no servidor ou na sua rede está bloqueando a porta 6379.")
        print("   4. O roteador do seu amigo não está configurado para encaminhar a porta 6379 para o servidor.")

    except redis.exceptions.TimeoutError:
        print(f"\n❌ Erro de Timeout: A conexão com {host}:{port} expirou.")
        print("\n   Isso geralmente significa que um firewall está bloqueando a conexão")
        print("   ou que a configuração de encaminhamento de porta (Port Forwarding) no roteador")
        print("   do seu amigo não está correta.")

    except Exception as e:
        print(f"\n❌ Ocorreu um erro inesperado: {e}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python test_redis_connection.py <IP_DO_SERVIDOR_REDIS>")
        sys.exit(1)
    
    server_ip = sys.argv[1]
    test_redis_connection(server_ip)
