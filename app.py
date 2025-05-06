from flask import Flask, request, jsonify
from flask_cors import CORS
import os
from pymongo import MongoClient
from dotenv import load_dotenv
from flask_bcrypt import Bcrypt
import datetime

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

#----------------------------------------------------------------------------------------------------------------------------------

@app.route('/fila_atendimento/finalizar', methods=['POST'])
def concluir_atendimento():
    db = connect_db()
    if not db:
        return jsonify({"erro": "Falha na conexão com o banco de dados"}), 500

    data = request.get_json()
    paciente_cpf = data.get('paciente_cpf') 
    
    if not paciente_cpf:
        return jsonify({"erro": "paciente_cpf é obrigatório"}), 400
    
    paciente_removido = remover_paciente_da_fila(db, paciente_cpf)
    if not paciente_removido:
        return jsonify({"erro": "Falha ao processar atendimento"}), 500
    
    if not atualizar_posicoes_fila(db):
        return jsonify({"erro": "Atendimento concluído, mas falha ao atualizar posições"}), 200
    
    return jsonify({
        "mensagem": "Atendimento concluído com sucesso",
        "paciente_removido": paciente_removido
    }), 200

#------------------------------------------------------------------------------------------------

@app.route('/pacientes/remover/paciente_cpf', methods=['DELETE'])
def remover_paciente_da_fila(db, paciente_cpf):
    fila_atendimento = db['fila_atendimento']
    paciente = fila_atendimento.find_one({"paciente_cpf": paciente_cpf})
    
    if not paciente:
        return None
    
    result = fila_atendimento.delete_one({"paciente_cpf": paciente_cpf})
    
    if result.deleted_count == 0:
        return None
    
    return {
        "cpf": paciente["paciente_cpf"],
        "nome": paciente["nome"],
        "triagem": paciente["triagem_oficial"]
    }

#------------------------------------------------------------------------------------------------

@app.route('/fila_atendimento/atualizar', methods=['PUT'])
def atualizar_posicoes_fila(db):
    fila_atendimento = db['fila_atendimento']
    pacientes_restantes = list(fila_atendimento.find().sort("posicao_fila", 1))
    
    
    try:
        for i, paciente in enumerate(pacientes_restantes, start=1):
            fila_atendimento.update_one(
                {"_id": paciente["_id"]},
                {"$set": {"posicao_fila": i}}
            )
        return True
    except Exception as e:
        print(f"Erro ao atualizar posições: {str(e)}")
        return False

#----------------------------------------------------------------------------------------------------------------------------------

if __name__ == '__main__':
    app.run(debug=True)