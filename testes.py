import pytest
from app import app
from flask_testing import TestCase

class TestCadastro(TestCase):
    def create_app(self):
        app.config['TESTING'] = True
        app.config['PRESERVE_CONTEXT_ON_EXCEPTION'] = False
        return app

    def test_cadastro_sucesso(self):
        dados = {
            "email": "teste@exemplo.com",
            "senha": "senha123",
            "nome_completo": "Teste"
        }
        response = self.client.post(
            "/cadastro",
            json=dados,
            content_type='application/json'
        )
        self.assert200(response)
        self.assertIn(b"msg", response.data)

    def test_cadastro_sem_email(self):
        dados = {
            "senha": "senha123",
            "nome_completo": "Teste"
        }
        response = self.client.post(
            "/cadastro",
            json=dados,
            content_type='application/json'
        )
        self.assert400(response)

    def test_cadastro_email_repetido(self):
        dados = {
            "email": "repetido@exemplo.com",
            "senha": "senha123",
            "nome_completo": "Teste"
        }
        # Primeiro cadastro
        self.client.post("/cadastro", json=dados)
        # Segundo cadastro
        response = self.client.post("/cadastro", json=dados)
        self.assert400(response)