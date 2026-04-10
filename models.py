from database import db
from datetime import datetime


class Cliente(db.Model):
    __tablename__ = 'clientes'

    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    morada = db.Column(db.String(200))
    telefone = db.Column(db.String(20))
    notas = db.Column(db.Text)
    frequencia = db.Column(db.String(20), default='pontual')  # semanal, quinzenal, pontual
    dia_semana = db.Column(db.String(20))  # segunda, terca, etc.
    hora_padrao = db.Column(db.String(5))  # HH:MM
    valor_padrao = db.Column(db.Float, default=0.0)
    ativo = db.Column(db.Boolean, default=True)
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)

    limpezas = db.relationship('Limpeza', backref='cliente', lazy=True, cascade='all, delete-orphan')

    def __repr__(self):
        return f'<Cliente {self.nome}>'


class Limpeza(db.Model):
    __tablename__ = 'limpezas'

    id = db.Column(db.Integer, primary_key=True)
    cliente_id = db.Column(db.Integer, db.ForeignKey('clientes.id'), nullable=False)
    data_hora = db.Column(db.DateTime, nullable=False)
    duracao_horas = db.Column(db.Float, default=2.0)
    notas = db.Column(db.Text)
    estado = db.Column(db.String(20), default='agendada')  # agendada, concluida, cancelada
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)

    pagamento = db.relationship('Pagamento', backref='limpeza', uselist=False, cascade='all, delete-orphan')

    def __repr__(self):
        return f'<Limpeza {self.cliente_id} {self.data_hora}>'


class Pagamento(db.Model):
    __tablename__ = 'pagamentos'

    id = db.Column(db.Integer, primary_key=True)
    limpeza_id = db.Column(db.Integer, db.ForeignKey('limpezas.id'), nullable=False)
    valor = db.Column(db.Float, default=0.0)
    pago = db.Column(db.Boolean, default=False)
    data_pagamento = db.Column(db.DateTime)
    metodo = db.Column(db.String(30), default='dinheiro')  # dinheiro, transferencia, outro
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<Pagamento limpeza={self.limpeza_id} pago={self.pago}>'
