import pytest
from app import app as flask_app
import mongomock
from flask_bcrypt import Bcrypt
from flask import json

bcrypt = Bcrypt()

# cliente para testes
@pytest.fixture
def client(monkeypatch):
    flask_app.config['TESTING'] = True

    mock_db = mongomock.MongoClient().db

    senha_hash = bcrypt.generate_password_hash("senha123").decode('utf-8')
    mock_db.pacientes.insert_one({
        "email": "teste@exemplo.com",
        "senha": senha_hash,
        "nome_completo": "Usuário Teste",
        "cpf": "12345678900",
        "celular": "11999998888",
        "endereco": "Rua de Teste, 123",
        "altura": 1.70,
        "peso": 60
    })

    monkeypatch.setattr('app.connect_db', lambda: mock_db)

    with flask_app.test_client() as client:
        yield client

# -----------------------------------------------------------------------------------------------------

# teste para cadastro
def test_cadastro(client):
    novo = {
        "email": "novo@example.com",
        "senha": "123456",
        "nome_completo": "Novo Usuário",
        "cpf": "00011122233",
        "celular": "11999998888",
        "endereco": "Rua Nova, 456"
    }

    response = client.post('/cadastro', json=novo)

    if response.status_code == 201:
        json_data = response.get_json()
        assert "cpf" in json_data
    else:
        assert response.status_code == 400

# -----------------------------------------------------------------------------------------------------

# testes para login
def test_login_sucesso(client):
    response = client.post('/login', json={
        'email': 'teste@exemplo.com',
        'senha': 'senha123'
    })
    assert response.status_code == 200
    assert response.get_json()['resposta'] == 'Login realizado com sucesso'
    assert response.get_json()['cpf'] == '12345678900'

def test_login_usuario_nao_encontrado(client):
    response = client.post('/login', json={
        'email': 'naoexiste@exemplo.com',
        'senha': 'senha123'
    })
    assert response.status_code == 404
    assert response.get_json()['resposta'] == 'Usuário não encontrado'

def test_login_senha_incorreta(client):
    response = client.post('/login', json={
        'email': 'teste@exemplo.com',
        'senha': 'senha_errada'
    })
    assert response.status_code == 401
    assert response.get_json()['resposta'] == 'Senha incorreta'

def test_login_dados_faltando(client):
    response = client.post('/login', json={
        'email': 'teste@exemplo.com'
    })
    assert response.status_code == 400
    assert response.get_json()['resposta'] == 'Email e senha são obrigatórios'

# -----------------------------------------------------------------------------------------------------

# testes para a triagem
def test_triagem_atualiza_dados_existentes(client):
    response = client.put('/triagem/12345678900', json={
        'altura': 1.75,
        'peso': 62
    })
    assert response.status_code == 200
    assert response.get_json()['resposta'] == 'Informações de saúde atualizadas com sucesso'

def test_triagem_adiciona_novos_dados(client):
    response = client.put('/triagem/12345678900', json={
        'pressao_arterial': '12x8',
        'alergias': 'nenhuma'
    })
    assert response.status_code == 200
    assert response.get_json()['resposta'] == 'Informações de saúde adicionadas com sucesso'

def test_triagem_sem_dados(client):
    response = client.put('/triagem/12345678900', json={})
    assert response.status_code == 400
    assert response.get_json()['resposta'] == 'Nenhuma informação de saúde fornecida'

def test_triagem_paciente_nao_encontrado(client):
    response = client.put('/triagem/00000000000', json={
        'altura': 1.70
    })
    assert response.status_code == 404
    assert response.get_json()['resposta'] == 'Paciente não encontrado'

# -----------------------------------------------------------------------------------------------------

