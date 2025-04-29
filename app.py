from flask import Flask, request
import os
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv('.cred') #carrega as variáveis de ambiente do aquivo .cred

mongo_uri = os.getenv('MONGO_URI') #vai pegar as informaçoes do .cred
db_name = os.getenv('DB_NAME', 'healthcenter')

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