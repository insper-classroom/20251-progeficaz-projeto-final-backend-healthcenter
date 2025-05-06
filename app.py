from flask import Flask, request, jsonify
from flask_cors import CORS
import os
from pymongo import MongoClient
from dotenv import load_dotenv
from flask_bcrypt import Bcrypt
import requests

load_dotenv()
mongo_uri = os.getenv('MONGO_URI')
db_name = os.getenv('DB_NAME', 'healthcenter')
app = Flask(__name__)
bcrypt = Bcrypt(app)
CORS(app)

def connect_db():
    try:
        print(f"Tentando conectar usando a URI: {mongo_uri}")
        client = MongoClient(mongo_uri)
        db = client[db_name]
        return db
    except Exception as e:
        print(f"Erro ao conectar ao MongoDB: {e}")
        return None
#----------------------------------------------------------------------------------------------------------------------------------
TEMPO_GRAVIDADE = {
    "leve": 20,
    "moderada": 40,
    "grave": 70
}
#----------------------------------------------------------------------------------------------------------------------------------
def distribuir_baldes(tempos, n_funcionarios):
    baldes = [0] * n_funcionarios
    for tempo in tempos:
        idx = baldes.index(min(baldes))
        baldes[idx] += tempo
    return baldes

#----------------------------------------------------------------------------------------------------------------------------------
#conectando com a api e função da triagem
def triagem_sintomas(sintomas: str):
    headers = {
        'Authorization': os.getenv('OPEN_AI_KEY'),
        'Content-Type': 'application/json'
    }

    data = {
        "messages": [
            {
                "role": "system",
                "content": (
                    "Você é um assistente de triagem médica. "
                    "Ao receber sintomas, você deve estimar a gravidade (leve, moderado, grave) "
                    "com base no relato e retornar apenas a situação do problema, como leve, moderado ou grave"
                )
            },
            {"role": "user", "content": sintomas}
        ]
    }

    try:
        response = requests.post(
            'https://openai-insper.openai.azure.com/openai/deployments/gpt-4o_ProgEficaz/chat/completions?api-version=2025-01-01-preview',
            #aqui precisa fazer algumas mudanças quando eu fizer o negócio la no azure
            headers=headers,
            json=data,
            timeout=10
        )
        response.raise_for_status()
        result = response.json()
        return result['choices'][0]['message']['content']
    except requests.exceptions.RequestException as e:
        return f"Erro ao conectar à API: {e}"
#----------------------------------------------------------------------------------------------------------------------------------
#BOTAO 1
@app.route('/login', methods=['POST'])
def login():
    db = connect_db()
    data = request.get_json()

    email = data.get('email')
    senha = data.get('senha')

    if not email or not senha:
        return jsonify({'msg': 'Email e senha são obrigatórios'}), 400

    # Primeiro verifica se é paciente
    paciente = db['pacientes'].find_one({'email': email})
    if paciente:
        senha_hash = paciente.get('senha')
        if bcrypt.check_password_hash(senha_hash, senha):
            return jsonify({
                'msg': 'Login realizado com sucesso',
                'cpf': paciente.get('cpf'),
                'tipo': 'paciente'
            }), 200
        else:
            return jsonify({'msg': 'Senha incorreta'}), 401

    # Depois tenta verificar se é funcionário
    funcionario = db['funcionarios'].find_one({'email': email})
    if funcionario:
        senha_hash = funcionario.get('senha')
        if bcrypt.check_password_hash(senha_hash, senha):
            return jsonify({
                'msg': 'Login realizado com sucesso',
                'cpf': funcionario.get('cpf'),
                'tipo': 'funcionario'
            }), 200
        else:
            return jsonify({'msg': 'Senha incorreta'}), 401

    return jsonify({'msg': 'Usuário não encontrado'}), 404


#----------------------------------------------------------------------------------------------------------------------------------
#BOTAO 2
@app.route('/cadastro', methods=['POST'])
def cadastro():
    db = connect_db()
    data = request.get_json()

    email = data.get('email')
    senha = data.get('senha')
    nome_completo = data.get('nome_completo')
    cpf = data.get('cpf')
    celular = data.get('celular')
    endereco = data.get('endereco')
    

    if not email or not senha:
        return jsonify({'msg': 'Email e senha são obrigatórios'}), 400

    if db['pacientes'].find_one({'email': email}):
        return jsonify({'msg': 'Usuário já existe'}), 400

    hashed = bcrypt.generate_password_hash(senha).decode('utf-8')

    paciente = {
        'email': email,
        'senha': hashed,
        'nome_completo': nome_completo,
        'cpf': cpf,
        'celular': celular,
        'endereco': endereco
    }

    db['pacientes'].insert_one(paciente)

    return jsonify({'msg': 'Usuário cadastrado com sucesso'}), 201
#----------------------------------------------------------------------------------------------------------------------------------
#BOTAO 3
@app.route('/triagem/<cpf>', methods=['POST'])
def entrar_fila_triagem(cpf):
    db = connect_db()
    fila_triagem = db['fila_triagem']
    fila_atendimento = db['fila_atendimento']
    funcionarios = db['funcionarios']
    pacientes = db['pacientes']

    data = request.get_json()
    sintomas = data.get("sintomas", "").strip()

    if not sintomas:
        return jsonify({"erro": "Sintomas não fornecidos"}), 400

    # 🔍 Chamada à IA para obter a gravidade
    resposta_ia = triagem_sintomas(sintomas)
    print("Resposta da IA:", resposta_ia)

    # Extrair a gravidade da resposta da IA
    for grav in TEMPO_GRAVIDADE.keys():
        if grav in resposta_ia.lower():
            gravidade = grav
            break
    else:
        return jsonify({"erro": "Não foi possível determinar a gravidade a partir dos sintomas"}), 400

    # Verifica se o paciente existe
    paciente_info = pacientes.find_one({"cpf": cpf})
    if not paciente_info:
        return jsonify({"erro": "Paciente não encontrado"}), 404

    # Verifica se já está em alguma fila
    if fila_triagem.find_one({"paciente_cpf": cpf}) or fila_atendimento.find_one({"paciente_cpf": cpf}):
        return jsonify({"erro": "Paciente já está em uma das filas"}), 400

    # ----- POSIÇÃO E TEMPO DE TRIAGEM -----
    posicao_triagem = fila_triagem.count_documents({}) + 1
    triagistas = funcionarios.count_documents({"disponível": True, "cargo": "triagem"})
    if triagistas == 0:
        return jsonify({"erro": "Nenhum funcionário disponível para triagem"}), 500

    tempo_triagem = ((posicao_triagem - 1) // triagistas) * 5 + 5

    # ----- PESSOAS NA FRENTE NO ATENDIMENTO -----
    fila_triagem_ordenada = list(fila_triagem.find().sort("posicao_fila", 1))
    fila_atend = list(fila_atendimento.find().sort("posicao_fila", 1))

    gravidades_antes = []

    for p in fila_atend:
        grav = p.get("triagem_oficial", "").lower().strip()
        if grav in TEMPO_GRAVIDADE:
            gravidades_antes.append(grav)

    for p in fila_triagem_ordenada:
        if p.get("posicao_fila", 999) < posicao_triagem:
            grav = p.get("triagemIA", "").lower().strip()
            if grav in TEMPO_GRAVIDADE:
                gravidades_antes.append(grav)

    atendentes = funcionarios.count_documents({"disponível": True, "cargo": "atendimento"})
    if atendentes == 0:
        return jsonify({"erro": "Nenhum funcionário disponível para atendimento"}), 500

    tempos_antes = [TEMPO_GRAVIDADE[g] for g in gravidades_antes]
    baldes = distribuir_baldes(tempos_antes, atendentes)
    espera = min(baldes)
    tempo_atendimento = espera + TEMPO_GRAVIDADE[gravidade]
    posicao_atendimento = len(gravidades_antes) + 1
    tempo_total = tempo_triagem + tempo_atendimento

    # ----- INSERIR NA FILA -----
    novo_paciente = {
        "paciente_cpf": cpf,
        "nome": paciente_info.get("nome_completo"),
        "triagemIA": gravidade,
        "posicao_fila": posicao_triagem
    }
    fila_triagem.insert_one(novo_paciente)

    return jsonify({
        "msg": "Paciente adicionado à fila de triagem com sucesso",
        "gravidade_estimada": gravidade,
        "resposta_ia": resposta_ia.strip(),
        "posicao_triagem": posicao_triagem,
        "tempo_triagem": f"{tempo_triagem} minutos",
        "posicao_atendimento": posicao_atendimento,
        "tempo_atendimento": f"{tempo_atendimento} minutos",
        "tempo_total_estimado": f"{tempo_total} minutos"
    }), 201

#----------------------------------------------------------------------------------------------------------------------------------
#BOTAO 4
@app.route('/triagem/<cpf>', methods=['PUT'])
def triagem(cpf):
    db = connect_db()
    data = request.get_json()

    atualizacoes = {}

    if 'altura' in data:
        atualizacoes['altura'] = data['altura']
    if 'peso' in data:
        atualizacoes['peso'] = data['peso']
    if 'pressao_arterial' in data:
        atualizacoes['pressao_arterial'] = data['pressao_arterial']
    if 'alergias' in data:
        atualizacoes['alergias'] = data['alergias']

    if not atualizacoes:
        return jsonify({'msg': 'Nenhuma informação de saúde fornecida'}), 400

    paciente = db['pacientes'].find_one({'cpf': cpf})
    if not paciente:
        return jsonify({'msg': 'Paciente não encontrado'}), 404

    # Verifica se algum dos campos ainda não existia no paciente
    campos_novos = [k for k in atualizacoes if k not in paciente]

    db['pacientes'].update_one({'cpf': cpf}, {'$set': atualizacoes})

    if campos_novos:
        return jsonify({'msg': 'Informações de saúde adicionadas com sucesso'}), 200
    else:
        return jsonify({'msg': 'Informações de saúde atualizadas com sucesso'}), 200

#--------------------------------------------------------------------------------------------------------------
# BOTAO 5
@app.route('/atendimento/<cpf>', methods=['DELETE'])
def remover_paciente_da_fila(cpf):
    db = connect_db()
    fila_atendimento = db['fila_atendimento']
    
    # Encontra o paciente
    paciente = fila_atendimento.find_one({"paciente_cpf": cpf})
    if not paciente:
        return jsonify({"erro": "Paciente não encontrado na fila de atendimento"}), 404

    posicao_removida = paciente.get("posicao_fila", None)
    
    # Remove o paciente da fila
    result = fila_atendimento.delete_one({"paciente_cpf": cpf})
    if result.deleted_count == 0:
        return jsonify({"erro": "Erro ao remover paciente"}), 500

    # Atualiza as posições de quem estava atrás
    fila_restante = list(fila_atendimento.find({"posicao_fila": {"$gt": posicao_removida}}))
    for p in fila_restante:
        nova_posicao = p["posicao_fila"] - 1
        fila_atendimento.update_one(
            {"paciente_cpf": p["paciente_cpf"]},
            {"$set": {"posicao_fila": nova_posicao}}
        )

    return jsonify({
        "msg": "Paciente removido com sucesso",
        "cpf": paciente["paciente_cpf"],
        "nome": paciente["nome"],
        "triagem": paciente["triagem_oficial"]
    }), 200


#--------------------------------------------------------------------------------------------------------------
# BOTAO 6 e 7
@app.route('/triagem/<cpf>', methods=['GET'])
def verifica_triagem(cpf):
    db = connect_db()
    fila_atendimento = db['fila_atendimento']
    funcionarios = db['funcionarios']

    # Verifica se o paciente está na fila de atendimento
    paciente = fila_atendimento.find_one({"paciente_cpf": cpf})
    if not paciente:
        return jsonify({"erro": "Paciente não está na fila de atendimento"}), 404

    triagem_oficial = paciente.get("triagem_oficial", "").lower().strip()

    if triagem_oficial not in TEMPO_GRAVIDADE:
        return jsonify({
            "msg": "A análise dos seus sintomas ainda não foi concluída... Por favor, tente novamente em alguns segundos."
        }), 202

    minha_posicao = paciente.get("posicao_fila", 999)
    fila_ordenada = list(fila_atendimento.find().sort("posicao_fila", 1))

    gravidades_antes = []
    for p in fila_ordenada:
        if p.get("posicao_fila", 999) < minha_posicao:
            grav = p.get("triagem_oficial", "").lower().strip()
            if grav in TEMPO_GRAVIDADE:
                gravidades_antes.append(grav)

    atendentes = funcionarios.count_documents({"disponível": True, "cargo": "atendimento"})
    if atendentes == 0:
        return jsonify({"erro": "Nenhum funcionário disponível para atendimento"}), 500

    # Calcula tempo estimado real usando distribuição dos tempos nas filas
    tempos_antes = [TEMPO_GRAVIDADE[g] for g in gravidades_antes]
    baldes = distribuir_baldes(tempos_antes, atendentes)
    menor_carga = min(baldes)

    # Adiciona seu próprio tempo de atendimento
    tempo_real = menor_carga + TEMPO_GRAVIDADE[triagem_oficial]

    return jsonify({
        "msg": "Sua triagem foi concluída!",
        "posicao_na_fila": minha_posicao,
        "tempo_estimado_espera": f"{tempo_real} minutos"
    }), 200
#--------------------------------------------------------------------------------------------------------------
# BOTAO 8
@app.route('/triagem_e_fila/<cpf>', methods=['PUT'])
def atualizar_triagem_e_fila(cpf):
    db = connect_db()
    fila_triagem = db['fila_triagem']
    fila_atendimento = db['fila_atendimento']

    data = request.get_json()
    nova_gravidade = data.get('triagem_oficial', '').lower().strip()

    if nova_gravidade not in TEMPO_GRAVIDADE:
        return jsonify({'erro': 'Gravidade inválida'}), 400

    # Busca o paciente na fila de triagem
    paciente = fila_triagem.find_one({"paciente_cpf": cpf})
    if not paciente:
        return jsonify({'erro': 'Paciente não encontrado na fila de triagem'}), 404

    posicao_removida = paciente.get("posicao_fila")

    # Atualiza a gravidade oficial e posição na fila de atendimento
    paciente['triagem_oficial'] = nova_gravidade
    nova_posicao = fila_atendimento.count_documents({}) + 1
    paciente['posicao_fila'] = nova_posicao
    fila_atendimento.insert_one(paciente)

    # Remove da fila de triagem
    fila_triagem.delete_one({"paciente_cpf": cpf})

    # Atualiza as posições de quem estava atrás na fila de triagem
    fila_triagem.update_many(
        {"posicao_fila": {"$gt": posicao_removida}},
        {"$inc": {"posicao_fila": -1}}
    )

    return jsonify({'msg': 'Paciente movido para a fila de atendimento com sucesso'}), 200
#--------------------------------------------------------------------------------------------------------------



if __name__ == '__main__':
    app.run(debug=True)
