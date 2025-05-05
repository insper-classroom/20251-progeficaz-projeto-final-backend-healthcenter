from flask import Flask, request, jsonify
from flask_cors import CORS
import os
from pymongo import MongoClient
from dotenv import load_dotenv
from flask_bcrypt import Bcrypt

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

TEMPO_GRAVIDADE = {
    "leve": 20,
    "moderada": 40,
    "grave": 70
}

def distribuir_baldes(tempos, n_funcionarios):
    baldes = [0] * n_funcionarios
    for tempo in tempos:
        idx = baldes.index(min(baldes))
        baldes[idx] += tempo
    return baldes
#ISSO EH OQ O PACIENTE VE, E ISSO NAO ADD A FILA
@app.route('/simular_estimativa/<cpf>', methods=['GET'])
def simular_estimativa(cpf):
    gravidade = request.args.get("gravidade", "").lower().strip()
    if gravidade not in TEMPO_GRAVIDADE:
        return jsonify({"erro": "Gravidade inválida"}), 400

    db = connect_db()
    fila_triagem = db['fila_triagem']
    fila_atendimento = db['fila_atendimento']
    funcionarios = db['funcionarios']

    posicao_triagem = fila_triagem.count_documents({}) + 1
    triagistas = funcionarios.count_documents({"disponível": True, "cargo": "triagem"})
    if triagistas == 0:
        return jsonify({"erro": "Nenhum funcionário disponível para triagem"}), 500

    tempo_triagem = ((posicao_triagem - 1) // triagistas) * 5 + 5

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

    return jsonify({
        "gravidade": gravidade,
        "posicao_triagem": posicao_triagem,
        "tempo_triagem": f"{tempo_triagem} minutos",
        "posicao_atendimento": posicao_atendimento,
        "tempo_atendimento": f"{tempo_atendimento} minutos",
        "tempo_total_estimado": f"{tempo_total} minutos"
    }), 200
#----------------------------------------------------------------------------------------------------------------------------------
#ISSO EH OQ O FUNCIONARIO VE E ADD A FILA
@app.route('/entrar_fila_triagem/<cpf>', methods=['POST'])
def entrar_fila_triagem(cpf):
    gravidade = request.args.get("gravidade", "").lower().strip()
    if gravidade not in TEMPO_GRAVIDADE:
        return jsonify({"erro": "Gravidade inválida"}), 400

    db = connect_db()
    fila_triagem = db['fila_triagem']
    fila_atendimento = db['fila_atendimento']
    funcionarios = db['funcionarios']
    pacientes = db['pacientes']

    # Verifica se o paciente existe
    paciente_info = pacientes.find_one({"cpf": cpf})
    if not paciente_info:
        return jsonify({"erro": "Paciente não encontrado"}), 404

    # Verifica se já está na fila
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
        "gravidade": gravidade,
        "posicao_triagem": posicao_triagem,
        "tempo_triagem": f"{tempo_triagem} minutos",
        "posicao_atendimento": posicao_atendimento,
        "tempo_atendimento": f"{tempo_atendimento} minutos",
        "tempo_total_estimado": f"{tempo_total} minutos"
    }), 201


#----------------------------------------------------------------------------------------------------------------------------------
#funcionario 
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

#----------------------------------------------------------------------------------------------------------------------------------
#referente a primeira tela
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

@app.route('/login', methods=['POST'])
def login():
    db = connect_db()
    data = request.get_json()

    email = data.get('email')
    senha = data.get('senha')

    if not email or not senha:
        return jsonify({'msg': 'Email e senha são obrigatórios'}), 400

    paciente = db['pacientes'].find_one({'email': email})
    if not paciente:
        return jsonify({'msg': 'Usuário não encontrado'}), 404

    senha_hash = paciente.get('senha')

    if not bcrypt.check_password_hash(senha_hash, senha):
        return jsonify({'msg': 'Senha incorreta'}), 401

    return jsonify({'msg': 'Login realizado com sucesso', 'cpf': paciente.get('cpf')}), 200

#--------------------------------------------------------------------------------------------------------------
#funcionario 
@app.route('/atualizar_triagem_e_fila/<cpf>', methods=['PUT'])
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
@app.route('/verifica_triagem/<cpf>', methods=['GET'])
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

    # Pega todas as pessoas com posição_fila menor que a do paciente
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

    tempos_antes = [TEMPO_GRAVIDADE[g] for g in gravidades_antes]
    baldes = distribuir_baldes(tempos_antes, atendentes)
    espera = min(baldes)

    return jsonify({
        "msg": "Sua triagem foi concluída!",
        "posicao_na_fila": minha_posicao,
        "tempo_estimado_espera": f"{espera} minutos"
    }), 200
#--------------------------------------------------------------------------------------------------------------





if __name__ == '__main__':
    app.run(debug=True)
