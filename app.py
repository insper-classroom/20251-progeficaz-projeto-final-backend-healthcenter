from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_jwt_extended import (
    JWTManager, create_access_token, jwt_required, get_jwt_identity
)
from flask_bcrypt import Bcrypt
import os
from pymongo import MongoClient
from dotenv import load_dotenv
import datetime

load_dotenv('.cred') #carrega as variáveis de ambiente do aquivo .cred

mongo_uri = os.getenv('MONGO_URI') #vai pegar as informaçoes do .cred
db_name = os.getenv('DB_NAME', 'healthcenter')

app = Flask(__name__)
# CORS(app)
bcrypt = Bcrypt(app)
app.config['JWT_SECRET_KEY'] = os.getenv('JWT_SECRET_KEY')
jwt = JWTManager(app)


def connect_db():
    try:
        print(f'Tentando conectar usando a URI: {mongo_uri}')
        client = MongoClient(mongo_uri)
        db = client[db_name]
        return db
    except Exception as e:
        print(f'Erro ao conectar ao MongoDB: {e}')
        return None

@app.route('/pacientes', methods=['GET'])
def get_pacientes():
    db = connect_db()
    if db is None:
        return {'erro': 'Erro ao conectar ao banco de dados'}, 500

    try:
        collection = db['pacientes']
        pacientes_cursor = collection.find({}, {'_id': 0})  #remove o campo _id da resposta
        pacientes = list(pacientes_cursor)

        if not pacientes:
            return {'erro': 'Nenhum paciente encontrado'}, 404
        return {'pacientes': pacientes}, 200
    except Exception as e:
        return {'erro': f'Erro ao consultar pacientes: {str(e)}'}, 500
    
@app.route('/cadastro', methods=['POST'])
def criar_conta():
    db = connect_db()
    
    data = request.get_json()
    
    # Dados obrigatórios
    email = data.get('email')
    senha = data.get('senha')
    
    # Dados adicionais
    nome_completo = data.get('nome_completo')
    cpf = data.get('cpf')
    celular = data.get('celular')
    endereco = data.get('endereco')
    altura = data.get('altura')
    peso = data.get('peso')
    idade = data.get('idade')
    pressao_arterial = data.get('pressao_arterial')
    alergias = data.get('alergias')

    # Validação dos campos obrigatórios
    if not email or not senha:
        return jsonify({'msg': 'Email e senha são obrigatórios'}), 400

    # Verificar se usuário já existe
    if db['pacientes'].find_one({'email': email}):
        return jsonify({'msg': 'Usuário já existe'}), 400

    # Criptografar senha
    hashed = bcrypt.generate_password_hash(senha).decode('utf-8')

    paciente = {
        'email': email,
        'senha': hashed,
        'nome_completo': nome_completo,
        'cpf': cpf,
        'celular': celular,
        'endereco': endereco,
        'altura': altura,
        'peso': peso,
        'idade': idade,
        'pressao_arterial': pressao_arterial,
        'alergias': alergias,
        'data_criacao': datetime.datetime.utcnow()
    }

    collection = db['pacientes']
    pacientes_cursor = collection.find({}, {'_id': 0}) 
    pacientes = list(pacientes_cursor)
    pacientes.insert_one(paciente)

    return jsonify({'msg': 'Usuário cadastrado com sucesso'}), 201

if __name__ == '__main__':
    app.run(debug=True)