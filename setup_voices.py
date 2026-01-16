# Arquivo: setup_voices.py
import os
import torch
import numpy as np
from kokoro import KPipeline

# --- CONFIGURAÇÃO ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(BASE_DIR, 'core', 'voices_custom')
os.makedirs(OUTPUT_DIR, exist_ok=True)

print("--- 🎚️ CONFIGURANDO MESA DE SOM LUNDERON ---")

# Inicializa o pipeline (baixa as vozes base americanas/britânicas para mistura)
# Usamos 'a' (Americano) pois ele tem a maior variedade de vetores para misturar
pipeline = KPipeline(lang_code='a') 

def get_vector(name):
    """Extrai o vetor numérico da voz base"""
    try:
        voice = pipeline.load_voice(name)
        if torch.is_tensor(voice):
            return voice.numpy()
        return voice
    except:
        print(f"Erro ao carregar base: {name}")
        return None

# --- RECEITAS DAS NOVAS VOZES ---
# A magia acontece aqui. Misturamos vozes existentes para criar novas.
mixes = [
    {
        "id": "br_imperador",
        "nome": "Imperador",
        # 60% Santa (Grave) + 40% Alex (Neutro) = Grave mas claro
        "receita": [("pm_santa", 0.60), ("pm_alex", 0.40)] 
    },
    {
        "id": "br_jornalista",
        "nome": "Jornalista",
        # 70% Alex (Neutro) + 30% George (Britânico sério) = Tom de autoridade
        "receita": [("pm_alex", 0.70), ("bm_george", 0.30)]
    },
    {
        "id": "br_influencer",
        "nome": "Influencer",
        # 50% Dora (Padrão) + 50% Bella (Americana aguda/jovem) = Voz TikTok
        "receita": [("pf_dora", 0.50), ("af_bella", 0.50)]
    },
    {
        "id": "br_podcast",
        "nome": "Podcast Suave",
        # 60% Dora + 40% Emma (Britânica suave) = Voz relaxante
        "receita": [("pf_dora", 0.60), ("bf_emma", 0.40)]
    }
]

# --- GERAÇÃO ---
for mix in mixes:
    print(f"🎛️  Mixando voz: {mix['nome']}...")
    final_vec = None
    
    for voz_base, peso in mix['receita']:
        vec = get_vector(voz_base)
        if vec is not None:
            if final_vec is None:
                final_vec = vec * peso
            else:
                final_vec += vec * peso
                
    if final_vec is not None:
        path = os.path.join(OUTPUT_DIR, f"{mix['id']}.npy")
        np.save(path, final_vec)
        print(f"   ✅ Salvo: {mix['id']}.npy")

print("\n--- VOZES IMPLEMENTADAS COM SUCESSO ---")