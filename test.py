import pytest
from app import app as flask_app
import mongomock
from flask_bcrypt import Bcrypt
from flask import json

bcrypt = Bcrypt()

@pytest.fixture
def client(monkeypatch):
    flask_app.config['TESTING'] = True

    mock_db = mongomock.MongoClient().db

    # Adiciona o banco simulado como atributo do app para uso nos testes
    flask_app.db = mock_db

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

    senha_func_hash = bcrypt.generate_password_hash("funcsenha").decode('utf-8')
    mock_db.funcionarios.insert_one({
        "email": "funcionario@exemplo.com",
        "senha": senha_func_hash,
        "nome_completo": "Funcionário Teste",
        "cpf": "98765432100",
        "celular": "11888887777",
        "endereco": "Rua Funcional, 789"
    })

    monkeypatch.setattr('app.connect_db', lambda: mock_db)

    with flask_app.test_client() as client:
        yield client
# -------------------------- TESTES DE CADASTRO -------------------------------

def test_cadastro_sucesso(client):
    novo = {
        "email": "novo@example.com",
        "senha": "123456",
        "nome_completo": "Novo Usuário",
        "cpf": "00011122233",
        "celular": "11999998888",
        "endereco": "Rua Nova, 456"
    }

    response = client.post('/cadastro', json=novo)
    print(response.status_code)
    print(response.get_json())

    assert response.status_code == 201
    json_data = response.get_json()

def test_cadastro_email_duplicado(client):
    duplicado = {
        "email": "teste@exemplo.com",
        "senha": "outrasenha",
        "nome_completo": "Duplicado",
        "cpf": "32165498700",
        "celular": "11999990000",
        "endereco": "Rua Copia, 999"
    }

    response = client.post('/cadastro', json=duplicado)
    assert response.status_code == 400


# ---------------------------- TESTES DE LOGIN -------------------------------

def test_login_sucesso_paciente(client):
    response = client.post('/login', json={
        'email': 'teste@exemplo.com',
        'senha': 'senha123'
    })
    assert response.status_code == 200
    data = response.get_json()
    assert data['msg'] == 'Login realizado com sucesso'
    assert data['cpf'] == '12345678900'
    assert data['tipo'] == 'paciente'


def test_login_sucesso_funcionario(client):
    response = client.post('/login', json={
        'email': 'funcionario@exemplo.com',
        'senha': 'funcsenha'
    })
    assert response.status_code == 200
    data = response.get_json()
    assert data['msg'] == 'Login realizado com sucesso'
    assert data['cpf'] == '98765432100'
    assert data['tipo'] == 'funcionario'


def test_login_senha_incorreta(client):
    response = client.post('/login', json={
        'email': 'teste@exemplo.com',
        'senha': 'errado'
    })
    assert response.status_code == 401
    assert response.get_json()['msg'] == 'Senha incorreta'


def test_login_usuario_nao_encontrado(client):
    response = client.post('/login', json={
        'email': 'naoexiste@exemplo.com',
        'senha': 'qualquer'
    })
    assert response.status_code == 404
    assert response.get_json()['msg'] == 'Usuário não encontrado'


def test_login_dados_faltando(client):
    response = client.post('/login', json={
        'email': 'teste@exemplo.com'
    })
    assert response.status_code == 400
    assert response.get_json()['msg'] == 'Email e senha são obrigatórios'


# -------------------------- TESTES VERIFICA_TRIAGEM --------------------------------

def test_verifica_triagem_paciente_nao_esta_na_fila(client):
    response = client.get('/triagem/99999999999')
    assert response.status_code == 404
    assert response.get_json()['erro'] == 'Paciente não está na fila de atendimento'


def test_verifica_triagem_nao_concluida(client):
    client.application.db['fila_atendimento'].insert_one({
        "paciente_cpf": "12345678900",
        "triagem_oficial": "",
        "posicao_fila": 1
    })

    response = client.get('/triagem/12345678900')
    assert response.status_code == 202
    assert "não foi concluída" in response.get_json()['msg']

def test_verifica_triagem_com_valor_nao_reconhecido(client):
    client.application.db['fila_atendimento'].insert_one({
        "paciente_cpf": "12312312399",
        "triagem_oficial": "invalida",
        "posicao_fila": 1
    })

    client.application.db['funcionarios'].insert_one({
        "disponível": True,
        "cargo": "atendimento"
    })

    response = client.get('/triagem/12312312399')
    assert response.status_code == 202
    assert "não foi concluída" in response.get_json()['msg']