from flask import Flask, request, jsonify
import os
from pymongo import MongoClient
from dotenv import load_dotenv
import requests

load_dotenv('.cred') #carrega as variáveis de ambiente do aquivo .cred

mongo_uri = os.getenv('MONGO_URI') #vai pegar as informaçoes do .cred
db_name = os.getenv('DB_NAME', 'healthcenter')

#conectando com o banco de dados 
def connect_db():
    try:
        print(f"Tentando conectar usando a URI: {mongo_uri}")
        client = MongoClient(mongo_uri)
        db = client[db_name]
        return db
    except Exception as e:
        print(f"Erro ao conectar ao MongoDB: {e}")
        return None
    
app = Flask(__name__)

#conectando com a api e função da triagem
def triagem_sintomas(sintomas: str, api_key: str) -> str:
    headers = {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json'
    }

    data = {
        "model": "gpt-3.5-turbo",
        "messages": [
            {
                "role": "system",
                "content": (
                    "Você é um assistente de triagem médica. "
                    "Ao receber sintomas, você deve estimar a gravidade (leve, moderado, grave) "
                    "com base no relato e justificar sua avaliação de forma concisa."
                )
            },
            {"role": "user", "content": sintomas}
        ]
    }

    try:
        response = requests.post(
            'https://api.openai.com/v1/chat/completions',
            headers=headers,
            json=data,
            timeout=10
        )
        response.raise_for_status()
        result = response.json()
        return result['choices'][0]['message']['content']
    except requests.exceptions.RequestException as e:
        return f"Erro ao conectar à API: {e}"

#recebe os sintomas e retorna o resultado da triagem
@app.route('/triagem', methods=['POST'])
def fazer_triagem():
    dados = request.get_json()
    sintomas = dados.get('sintomas', '')
    api_key = 'sua-chave-aqui'  #colocar a variável de confiança do .cred

    resultado = triagem_sintomas(sintomas, api_key)
    return jsonify({'resultado': resultado})

@app.route('/pacientes', methods=['GET'])
def get_pacientes():
    db = connect_db()
    if db is None:
        return {"erro": "Erro ao conectar ao banco de dados"}, 500

    try:
        collection = db['pacientes']
        pacientes_cursor = collection.find({}, {"_id": 0})  #remove o campo _id da resposta
        pacientes = list(pacientes_cursor)

        if not pacientes:
            return {"erro": "Nenhum paciente encontrado"}, 404
        return {"pacientes": pacientes}, 200
    except Exception as e:
        return {"erro": f"Erro ao consultar pacientes: {str(e)}"}, 500

if __name__ == '__main__':
    app.run(debug=True)