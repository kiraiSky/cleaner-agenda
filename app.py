from flask import Flask, render_template, request, redirect, url_for, jsonify, flash, session
from database import db, init_db
from models import Cliente, Limpeza, Pagamento
from datetime import datetime, timedelta, date
import os

# Carregar variáveis de ambiente do .env se existir
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///agenda.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.secret_key = os.environ.get('SECRET_KEY', 'agenda-limpezas-secret-2024')

init_db(app)

DIAS_SEMANA = {
    'segunda': 0, 'terca': 1, 'quarta': 2,
    'quinta': 3, 'sexta': 4, 'sabado': 5, 'domingo': 6
}


def gerar_limpezas_recorrentes(cliente, semanas=8):
    """Gera limpezas recorrentes para as próximas N semanas (suporta múltiplos dias)."""
    if cliente.frequencia == 'pontual' or not cliente.dia_semana:
        return
    hoje = date.today()
    hora = datetime.strptime(cliente.hora_padrao or '09:00', '%H:%M').time()
    intervalo = 1 if cliente.frequencia == 'semanal' else 2
    dias_lista = [d.strip() for d in cliente.dia_semana.split(',') if d.strip()]
    datas_existentes = {l.data_hora.date() for l in cliente.limpezas}

    for dia_nome in dias_lista:
        dia_alvo = DIAS_SEMANA.get(dia_nome, 0)
        dias_ate = (dia_alvo - hoje.weekday()) % 7
        if dias_ate == 0:
            dias_ate = 7 * intervalo
        proximo = hoje + timedelta(days=dias_ate)

        for i in range(semanas // intervalo):
            data_limpeza = proximo + timedelta(weeks=i * intervalo)
            if data_limpeza not in datas_existentes:
                dt = datetime.combine(data_limpeza, hora)
                limpeza = Limpeza(
                    cliente_id=cliente.id,
                    data_hora=dt,
                    duracao_horas=2.0
                )
                db.session.add(limpeza)
                pagamento = Pagamento(
                    limpeza=limpeza,
                    valor=cliente.valor_padrao or 0.0
                )
                db.session.add(pagamento)
                datas_existentes.add(data_limpeza)
    db.session.commit()


# ─── Dashboard ───────────────────────────────────────────────
@app.route('/')
def dashboard():
    hoje = datetime.now().date()
    inicio_semana = hoje
    fim_semana = hoje + timedelta(days=7)

    limpezas_hoje = Limpeza.query.filter(
        db.func.date(Limpeza.data_hora) == hoje,
        Limpeza.estado == 'agendada'
    ).order_by(Limpeza.data_hora).all()

    proximas = Limpeza.query.filter(
        Limpeza.data_hora >= datetime.combine(inicio_semana, datetime.min.time()),
        Limpeza.data_hora <= datetime.combine(fim_semana, datetime.max.time()),
        Limpeza.estado == 'agendada'
    ).order_by(Limpeza.data_hora).all()

    # pagamentos em atraso: limpezas concluídas ou passadas não pagas
    atrasados = (
        Pagamento.query
        .join(Limpeza)
        .filter(Pagamento.pago == False)
        .filter(Limpeza.data_hora < datetime.now())
        .filter(Limpeza.estado != 'cancelada')
        .all()
    )

    inicio_mes = hoje.replace(day=1)
    limpezas_mes = Limpeza.query.filter(
        db.func.date(Limpeza.data_hora) >= inicio_mes,
        db.func.date(Limpeza.data_hora) <= hoje
    ).count()

    total_recebido = db.session.query(db.func.sum(Pagamento.valor)).filter(
        Pagamento.pago == True
    ).scalar() or 0.0

    total_falta = db.session.query(db.func.sum(Pagamento.valor)).join(Limpeza).filter(
        Pagamento.pago == False,
        Limpeza.estado != 'cancelada'
    ).scalar() or 0.0

    return render_template('dashboard.html',
        limpezas_hoje=limpezas_hoje,
        proximas=proximas,
        atrasados=atrasados,
        limpezas_mes=limpezas_mes,
        total_recebido=total_recebido,
        total_falta=total_falta,
        hoje=hoje
    )


# ─── Clientes ────────────────────────────────────────────────
@app.route('/clientes')
def clientes():
    todos = Cliente.query.order_by(Cliente.nome).all()
    return render_template('clientes.html', clientes=todos)


@app.route('/clientes/novo', methods=['GET', 'POST'])
def cliente_novo():
    if request.method == 'POST':
        cliente = Cliente(
            nome=request.form['nome'],
            morada=request.form.get('morada', ''),
            telefone=request.form.get('telefone', ''),
            notas=request.form.get('notas', ''),
            frequencia=request.form.get('frequencia', 'pontual'),
            dia_semana=','.join(request.form.getlist('dia_semana')) or None,
            hora_padrao=request.form.get('hora_padrao', '09:00'),
            valor_padrao=float(request.form.get('valor_padrao', 0) or 0)
        )
        db.session.add(cliente)
        db.session.commit()
        gerar_limpezas_recorrentes(cliente)
        flash(f'Cliente {cliente.nome} criado com sucesso!', 'success')
        return redirect(url_for('clientes'))
    return render_template('cliente_form.html', cliente=None)


@app.route('/clientes/<int:id>/editar', methods=['GET', 'POST'])
def cliente_editar(id):
    cliente = Cliente.query.get_or_404(id)
    if request.method == 'POST':
        cliente.nome = request.form['nome']
        cliente.morada = request.form.get('morada', '')
        cliente.telefone = request.form.get('telefone', '')
        cliente.notas = request.form.get('notas', '')
        cliente.frequencia = request.form.get('frequencia', 'pontual')
        cliente.dia_semana = ','.join(request.form.getlist('dia_semana')) or None
        cliente.hora_padrao = request.form.get('hora_padrao', '09:00')
        cliente.valor_padrao = float(request.form.get('valor_padrao', 0) or 0)
        cliente.ativo = 'ativo' in request.form
        db.session.commit()
        flash(f'Cliente {cliente.nome} atualizado!', 'success')
        return redirect(url_for('clientes'))
    return render_template('cliente_form.html', cliente=cliente)


@app.route('/clientes/<int:id>/apagar', methods=['POST'])
def cliente_apagar(id):
    cliente = Cliente.query.get_or_404(id)
    nome = cliente.nome
    db.session.delete(cliente)
    db.session.commit()
    flash(f'Cliente {nome} removido.', 'info')
    return redirect(url_for('clientes'))


@app.route('/clientes/<int:id>')
def cliente_detalhe(id):
    cliente = Cliente.query.get_or_404(id)
    limpezas = Limpeza.query.filter_by(cliente_id=id).order_by(Limpeza.data_hora.desc()).all()
    return render_template('cliente_detalhe.html', cliente=cliente, limpezas=limpezas)


# ─── Agenda ──────────────────────────────────────────────────
@app.route('/agenda')
def agenda():
    clientes_ativos = Cliente.query.filter_by(ativo=True).order_by(Cliente.nome).all()
    try:
        from google_calendar import is_connected
        google_connected = is_connected()
    except Exception:
        google_connected = False
    return render_template('agenda.html', clientes=clientes_ativos, google_connected=google_connected)


@app.route('/api/eventos')
def api_eventos():
    limpezas = Limpeza.query.filter(Limpeza.estado != 'cancelada').all()
    eventos = []
    cores = {'agendada': '#0d6efd', 'concluida': '#198754', 'cancelada': '#6c757d'}
    for l in limpezas:
        eventos.append({
            'id': l.id,
            'title': l.cliente.nome,
            'start': l.data_hora.isoformat(),
            'end': (l.data_hora + timedelta(hours=l.duracao_horas)).isoformat(),
            'color': cores.get(l.estado, '#0d6efd'),
            'extendedProps': {
                'estado': l.estado,
                'notas': l.notas or '',
                'pago': l.pagamento.pago if l.pagamento else False,
                'valor': l.pagamento.valor if l.pagamento else 0
            }
        })
    return jsonify(eventos)


@app.route('/limpezas/nova', methods=['GET', 'POST'])
def limpeza_nova():
    if request.method == 'POST':
        data_str = request.form['data_hora']
        dt = datetime.strptime(data_str, '%Y-%m-%dT%H:%M')
        limpeza = Limpeza(
            cliente_id=int(request.form['cliente_id']),
            data_hora=dt,
            duracao_horas=float(request.form.get('duracao_horas', 2)),
            notas=request.form.get('notas', '')
        )
        db.session.add(limpeza)
        db.session.flush()
        pagamento = Pagamento(
            limpeza_id=limpeza.id,
            valor=float(request.form.get('valor', 0) or 0),
            metodo=request.form.get('metodo', 'dinheiro')
        )
        db.session.add(pagamento)
        db.session.commit()
        _sync_limpeza_auto(limpeza)
        db.session.commit()
        flash('Limpeza agendada!', 'success')
        return redirect(url_for('agenda'))
    clientes_ativos = Cliente.query.filter_by(ativo=True).order_by(Cliente.nome).all()
    data_pre = request.args.get('data', '')
    cliente_pre = request.args.get('cliente', '')
    return render_template('limpeza_form.html', clientes=clientes_ativos, limpeza=None, data_pre=data_pre, cliente_pre=cliente_pre)


@app.route('/limpezas/<int:id>/editar', methods=['GET', 'POST'])
def limpeza_editar(id):
    limpeza = Limpeza.query.get_or_404(id)
    if request.method == 'POST':
        data_str = request.form['data_hora']
        limpeza.data_hora = datetime.strptime(data_str, '%Y-%m-%dT%H:%M')
        limpeza.cliente_id = int(request.form['cliente_id'])
        limpeza.duracao_horas = float(request.form.get('duracao_horas', 2))
        limpeza.notas = request.form.get('notas', '')
        limpeza.estado = request.form.get('estado', 'agendada')
        if limpeza.pagamento:
            limpeza.pagamento.valor = float(request.form.get('valor', 0) or 0)
            limpeza.pagamento.metodo = request.form.get('metodo', 'dinheiro')
        db.session.commit()
        _sync_limpeza_auto(limpeza)
        db.session.commit()
        flash('Limpeza atualizada!', 'success')
        return redirect(url_for('agenda'))
    clientes_ativos = Cliente.query.filter_by(ativo=True).order_by(Cliente.nome).all()
    return render_template('limpeza_form.html', clientes=clientes_ativos, limpeza=limpeza, data_pre='')


@app.route('/limpezas/<int:id>/concluir', methods=['POST'])
def limpeza_concluir(id):
    limpeza = Limpeza.query.get_or_404(id)
    limpeza.estado = 'concluida'
    db.session.commit()
    flash('Limpeza marcada como concluída!', 'success')
    return redirect(request.referrer or url_for('dashboard'))


@app.route('/limpezas/<int:id>/apagar', methods=['POST'])
def limpeza_apagar(id):
    limpeza = Limpeza.query.get_or_404(id)
    _delete_event_auto(limpeza)
    db.session.delete(limpeza)
    db.session.commit()
    flash('Limpeza removida.', 'info')
    return redirect(request.referrer or url_for('agenda'))


# ─── Pagamentos ───────────────────────────────────────────────
@app.route('/pagamentos')
def pagamentos():
    filtro = request.args.get('filtro', 'todos')
    query = Pagamento.query.join(Limpeza).filter(Limpeza.estado != 'cancelada')
    if filtro == 'pagos':
        query = query.filter(Pagamento.pago == True)
    elif filtro == 'por_pagar':
        query = query.filter(Pagamento.pago == False)
    lista = query.order_by(Limpeza.data_hora.desc()).all()

    total_pago = sum(p.valor for p in lista if p.pago)
    total_falta = sum(p.valor for p in lista if not p.pago)

    return render_template('pagamentos.html',
        pagamentos=lista, filtro=filtro,
        total_pago=total_pago, total_falta=total_falta
    )


@app.route('/pagamentos/<int:id>/pagar', methods=['POST'])
def pagamento_pagar(id):
    pagamento = Pagamento.query.get_or_404(id)
    pagamento.pago = True
    pagamento.data_pagamento = datetime.now()
    pagamento.metodo = request.form.get('metodo', pagamento.metodo)
    db.session.commit()
    flash('Pagamento registado!', 'success')
    return redirect(request.referrer or url_for('pagamentos'))


@app.route('/pagamentos/<int:id>/cancelar', methods=['POST'])
def pagamento_cancelar(id):
    pagamento = Pagamento.query.get_or_404(id)
    pagamento.pago = False
    pagamento.data_pagamento = None
    db.session.commit()
    flash('Pagamento revertido.', 'info')
    return redirect(request.referrer or url_for('pagamentos'))


# ─── API Lembretes ────────────────────────────────────────────
@app.route('/api/lembretes')
def api_lembretes():
    agora = datetime.now()
    limite = agora + timedelta(hours=24)
    limpezas = Limpeza.query.filter(
        Limpeza.data_hora >= agora,
        Limpeza.data_hora <= limite,
        Limpeza.estado == 'agendada'
    ).order_by(Limpeza.data_hora).all()
    resultado = []
    for l in limpezas:
        resultado.append({
            'id': l.id,
            'cliente': l.cliente.nome,
            'data_hora': l.data_hora.strftime('%d/%m %H:%M'),
            'minutos': int((l.data_hora - agora).total_seconds() / 60)
        })
    return jsonify(resultado)


# ─── Google Calendar ─────────────────────────────────────────
@app.route('/google/auth')
def google_auth():
    """Inicia o fluxo OAuth2 com o Google."""
    try:
        from google_calendar import get_flow
        redirect_uri = url_for('google_callback', _external=True)
        flow = get_flow(redirect_uri)
        auth_url, state = flow.authorization_url(
            access_type='offline',
            include_granted_scopes='true',
            prompt='consent'
        )
        session['google_oauth_state'] = state
        return redirect(auth_url)
    except Exception as e:
        flash(f'Erro ao iniciar autenticação Google: {str(e)}', 'danger')
        return redirect(url_for('agenda'))


@app.route('/google/callback')
def google_callback():
    """Callback OAuth2 — guarda o token."""
    try:
        from google_calendar import get_flow, save_credentials
        redirect_uri = url_for('google_callback', _external=True)
        flow = get_flow(redirect_uri)
        flow.fetch_token(authorization_response=request.url)
        save_credentials(flow.credentials)
        flash('Google Agenda ligada com sucesso! 🎉', 'success')
    except Exception as e:
        flash(f'Erro na autenticação: {str(e)}', 'danger')
    return redirect(url_for('agenda'))


@app.route('/google/sync', methods=['POST'])
def google_sync():
    """Sincroniza todas as limpezas agendadas para o Google Calendar."""
    try:
        from google_calendar import sync_all, is_connected
        if not is_connected():
            flash('Não estás ligado ao Google. Liga primeiro.', 'danger')
            return redirect(url_for('agenda'))
        limpezas = Limpeza.query.filter(Limpeza.estado != 'cancelada').all()
        sucesso, falha = sync_all(limpezas)
        db.session.commit()
        if falha == 0:
            flash(f'✓ {sucesso} limpeza(s) sincronizada(s) com o Google Agenda!', 'success')
        else:
            flash(f'✓ {sucesso} sincronizadas, {falha} com erro.', 'info')
    except Exception as e:
        flash(f'Erro na sincronização: {str(e)}', 'danger')
    return redirect(url_for('agenda'))


@app.route('/google/disconnect', methods=['POST'])
def google_disconnect():
    """Remove a ligação com o Google."""
    import os
    if os.path.exists('token.json'):
        os.remove('token.json')
    flash('Google Agenda desligada.', 'info')
    return redirect(url_for('agenda'))


def _sync_limpeza_auto(limpeza):
    """Sincroniza automaticamente se estiver ligado ao Google."""
    try:
        from google_calendar import is_connected, sync_limpeza
        if is_connected():
            event_id = sync_limpeza(limpeza)
            if event_id:
                limpeza.google_event_id = event_id
    except Exception:
        pass


def _delete_event_auto(limpeza):
    """Apaga o evento do Google Calendar se existir."""
    try:
        from google_calendar import delete_event
        if limpeza.google_event_id:
            delete_event(limpeza.google_event_id)
    except Exception:
        pass


# ─── Service Worker (PWA) ─────────────────────────────────────
@app.route('/sw.js')
def service_worker():
    from flask import send_from_directory
    return send_from_directory('static', 'sw.js', mimetype='application/javascript')


if __name__ == '__main__':
    import socket
    hostname = socket.gethostname()
    try:
        ip_local = socket.gethostbyname(hostname)
    except Exception:
        ip_local = '127.0.0.1'
    print(f'\n*** Agenda de Limpezas a correr! ***')
    print(f'   PC:        http://localhost:5000')
    print(f'   Telemovel: http://{ip_local}:5000\n')
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('RENDER') is None
    app.run(debug=debug, host='0.0.0.0', port=port, threaded=True)
